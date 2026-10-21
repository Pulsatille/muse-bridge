# -*- coding: utf-8 -*-
"""keepalive.py — Muse 账号自动保活（滑动会话 + 凭证保鲜）

原理：Muse 登录态（hatch_sess）在服务端会滑动续期——只要定期用该 profile 打开
muse.ai 并让 SPA 完整加载，会话即被刷新，凭证永不过期（实测 10-14 登录 → 10-21
仍有效且 days_left 由 26.8 回升到 29.8）。本模块把"打开→校验→重新导出 auth.json"
做成无人值守 tick，配合 cron 每 N 小时跑一次即可 24h 保活。

用法:
  python -m muse_bridge.keepalive tick [--account ID]   逐号保活（缺省全部账号）
  输出: 每号一行 JSON + 汇总行；任一账号登录墙 → 退出码 1（供 cron 错误审计捕获）

内存: 每次 tick 起一个 headless Chromium（~150-250MB 峰值，15-30s），跑完即全部释放，
无常驻进程——24h 保活不需要常驻内存。
"""
import sys, os, json, time, argparse
from pathlib import Path

from muse_bridge.cred_extract import (BASE, CHROME, UA, MUSE_URL, load_reg, save_reg,
                                      _resolve, days_left, dump_state)

def ensure_dirs():
    (BASE / "out").mkdir(parents=True, exist_ok=True)

def tick_account(p, aid, cfg):
    """返回 dict 结果。打开 profile→muse.ai→等 composer→storage_state 保鲜。
    p 为外层 sync_playwright 实例（复用，不可嵌套打开）。"""
    prof = _resolve(cfg.get("profile")) or str(BASE / "chrome-full")
    auth = _resolve(cfg.get("auth")) or str(BASE / "accounts" / aid / "auth.json")
    res = {"account": aid, "ok": False, "logged_in": False, "login_wall": False,
           "profile_exists": bool(prof and Path(prof).exists()), "auth": auth,
           "days_before": days_left(auth) if Path(auth).exists() else None,
           "days_after": None, "cookies": 0, "expires_fixed": 0, "error": None}
    if not res["profile_exists"]:
        res["error"] = "profile missing (run cred_extract login first)"
        return res
    proxy = cfg.get("proxy")
    kw = dict(user_data_dir=prof, executable_path=CHROME, headless=True,
              args=["--headless=new", "--disable-gpu", "--no-first-run", "--window-size=1280,900"],
              ignore_default_args=["--enable-automation"], locale="zh-CN", user_agent=UA)
    if proxy:
        kw["proxy"] = {"server": proxy}
    ctx = p.chromium.launch_persistent_context(**kw)
    try:
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            pg.goto(MUSE_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        # 最多等 40s：composer 出现=登录；登录输入框出现=登录墙
        end = time.time() + 40
        while time.time() < end:
            try:
                if pg.query_selector("textarea[placeholder*='消息']") or pg.query_selector("textarea"):
                    res["logged_in"] = True
                    break
                if pg.query_selector("input[aria-label='手机号或邮箱']"):
                    res["login_wall"] = True
                    break
            except Exception:
                pass
            time.sleep(3)
        if res["logged_in"]:
            time.sleep(4)  # 等 SPA 写全 localStorage / 刷新 cookie
            sd, fixed = dump_state(ctx, auth)
            res["ok"] = True
            res["cookies"] = len(sd.get("cookies", []))
            res["expires_fixed"] = fixed
            res["days_after"] = days_left(auth)
            # registry 记录保鲜时间
            r = load_reg()
            r.setdefault("accounts", {}).setdefault(aid, {})["keepalive_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            save_reg(r)
        elif res["login_wall"]:
            res["error"] = "login_wall: session expired, need re-login (cred_extract login %s)" % aid
        else:
            res["error"] = "timeout: neither composer nor login wall detected"
    finally:
        ctx.close()
    return res

def cmd_tick(a):
    ensure_dirs()
    r = load_reg()
    ids = [a.account] if a.account else list(r.get("accounts", {}).keys())
    if not ids:
        print(json.dumps({"ok": False, "error": "no accounts in registry"}))
        return 1
    results = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        for aid in ids:
            cfg = r.get("accounts", {}).get(aid, {})
            res = tick_account(p, aid, cfg)
            results.append(res)
            print(json.dumps(res, ensure_ascii=False))
    ok_n = sum(1 for x in results if x["ok"])
    dead = [x["account"] for x in results if not x["ok"]]
    default_ok = any(x["account"] == r.get("default") and x["ok"] for x in results)
    summary = {"ok": (ok_n >= 1 and default_ok) or (not r.get("default") and ok_n >= 1),
               "total": len(results), "refreshed": ok_n, "dead": dead}
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["ok"] else 1

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("tick"); x.add_argument("--account", default=None)
    a = ap.parse_args()
    return {"tick": cmd_tick}[a.cmd](a) or 0

if __name__ == "__main__":
    sys.exit(main())
