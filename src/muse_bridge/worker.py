#!/usr/bin/env python3
"""Muse 网页会话 worker v2（被 muse_bridge_mcp_server.py 子进程调用）。
v2 变更：多账号（registry.json）+ 代理分散 + send/new_chat 稳定性加固 + 会话剩余天数。
用法: muse_worker.py send "<文本>" [--new-chat] [--account ID]
      muse_worker.py poll [--timeout N] [--account ID]
      muse_worker.py status [--account ID]
      muse_worker.py accounts
输出: 最后一行单个 JSON。
账号解析优先序: --account 参数 > MUSE_ACCOUNT 环境变量 > registry.default > 内置 chrome-full。
"""
import sys, os, time, json, uuid, argparse
from pathlib import Path

BASE = Path(os.environ.get("MUSE_HOME", str(Path(__file__).resolve().parents[2])))
REGISTRY = BASE / "accounts" / "registry.json"
LEGACY_PROFILE = str(BASE / "chrome-full")
CHROME = os.environ.get("MUSE_CHROME") or None
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")

_POOL_CTX = {"aid": None}

def emit(obj):
    # pool 选路时自动回报本次结果（成功清失败计数，失败进冷却避让）
    if _POOL_CTX["aid"]:
        pool_report(_POOL_CTX["aid"], bool(obj.get("ok")))
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(0 if obj.get("ok") else 1)

def load_reg():
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _pool_mod():
    """pool 模块健壮导入：既支持 `-m muse_bridge.worker`（包导入），
    也支持被 mcp_server 以文件路径运行（sys.path[0]=本目录，直接 import pool）。"""
    try:
        from muse_bridge import pool
        return pool
    except Exception:
        try:
            import pool
            return pool
        except Exception:
            return None


def resolve_account(aid=None):
    reg = load_reg()
    aid = aid or os.environ.get("MUSE_ACCOUNT") or reg.get("default") or None
    # account="pool" → 自动选路（中转站式：健康度最优账号，失败冷却避让）
    if aid == "pool":
        m = _pool_mod()
        if m:
            aid = m.pick().get("account") or reg.get("default")
        else:
            aid = reg.get("default")
    if aid and aid in reg.get("accounts", {}):
        cfg = reg["accounts"][aid]
        return aid, cfg.get("profile") or LEGACY_PROFILE, cfg.get("proxy"), cfg.get("auth")
    return aid, LEGACY_PROFILE, None, None


def pool_report(aid, ok):
    """上报本次使用结果给 pool。仅由 emit 在 _POOL_CTX 置位时调用（pool 选路场景）。"""
    m = _pool_mod()
    if m and aid:
        try:
            m.record(aid, ok)
        except Exception:
            pass

def open_ctx(p, profile, proxy=None):
    kw = dict(user_data_dir=profile, executable_path=CHROME, headless=True,
              args=["--headless=new", "--disable-gpu", "--no-first-run", "--window-size=1280,900"],
              ignore_default_args=["--enable-automation"], locale="zh-CN", user_agent=UA)
    if proxy:
        kw["proxy"] = {"server": proxy}
    return p.chromium.launch_persistent_context(**kw)

def find_box(pg, tries=10):
    for _ in range(tries):
        try:
            b = pg.query_selector("textarea[placeholder*='消息']") or pg.query_selector("textarea")
            if b:
                return b
        except Exception:
            return None  # 导航中句柄失效，交给上层重试
        time.sleep(3)
    return None

def new_chat(pg):
    """点『聊天』开新会话；导航后等 composer 重新就绪（v2 修复：不再复用失效句柄）。"""
    try:
        btn = pg.query_selector("[aria-label*='聊天']") or pg.query_selector("text=打开聊天和旁聊")
        if not btn:
            return False
        btn.click(timeout=4000)
        try:
            pg.wait_for_selector("textarea", timeout=15000)
        except Exception:
            pass
        time.sleep(1.5)
        return True
    except Exception:
        return False

def sess_days_left(auth_path):
    try:
        d = json.loads(Path(auth_path).read_text(encoding="utf-8"))
        for c in d.get("cookies", []):
            if c["name"] == "hatch_sess" and c.get("expires", 0) > 0:
                return round((c["expires"] - time.time()) / 86400, 1)
    except Exception:
        pass
    return None

def send_with_verify(pg, text, marker):
    """输入→校验→回车→校验离开输入框；失败重做一次。返回 delivered。"""
    for attempt in (1, 2):
        box = find_box(pg)
        if not box:
            time.sleep(3); continue
        full = f"{marker} {text}" if text else marker
        try:
            box.click(timeout=5000)
        except Exception:
            continue
        time.sleep(0.4)
        try:
            pg.keyboard.type(full, delay=12)
        except Exception:
            continue
        time.sleep(0.5)
        try:
            got = box.evaluate("el=>el.value") or ""
        except Exception:
            got = ""
        if marker not in got:  # 没进输入框 → 重试整轮
            continue
        try:
            pg.keyboard.press("Enter")
        except Exception:
            pass
        # 等 marker 出现在页面且离开输入框
        end = time.time() + 45
        while time.time() < end:
            time.sleep(3)
            try:
                body = pg.evaluate("()=>document.body.innerText")
                cur_val = (pg.evaluate("()=>{const b=document.querySelector('textarea');return b?b.value:''}") or "")
            except Exception:
                continue
            if marker in body and marker not in cur_val:
                return True
        # 补一次回车再给 20 秒（Enter 可能丢）
        try:
            pg.keyboard.press("Enter")
        except Exception:
            pass
        end2 = time.time() + 20
        while time.time() < end2:
            time.sleep(3)
            try:
                if marker in pg.evaluate("()=>document.body.innerText"):
                    return True
            except Exception:
                pass
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["send", "poll", "status", "accounts"])
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--new-chat", action="store_true")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--account", default=None)
    a = ap.parse_args()

    aid, profile, proxy, auth = resolve_account(a.account)

    if a.cmd == "accounts":
        reg = load_reg()
        out = []
        for k, cfg in reg.get("accounts", {}).items():
            out.append({"id": k, "label": cfg.get("label", ""), "proxy": bool(cfg.get("proxy")),
                        "days_left": sess_days_left(cfg.get("auth", "")),
                        "default": k == reg.get("default")})
        emit({"ok": True, "accounts": out, "current": aid})

    from playwright.sync_api import sync_playwright
    if (a.account == "pool") or os.environ.get("MUSE_ACCOUNT") == "pool":
        _POOL_CTX["aid"] = aid  # 后续 emit 自动把本次 ok/fail 回报给 pool
    with sync_playwright() as p:
        ctx = open_ctx(p, profile, proxy)
        try:
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            pg.goto("https://muse.ai", wait_until="domcontentloaded", timeout=60000)

            if a.cmd == "poll":
                last, stable, end = "", 0, time.time() + a.timeout
                time.sleep(6)
                while time.time() < end:
                    try:
                        cur = pg.evaluate("""()=>{const m=[...document.querySelectorAll('[class*=message],[data-message],[role=listitem]')];return m.length?m[m.length-1].innerText:''}""")
                    except Exception:
                        time.sleep(3); continue
                    if cur and cur == last: stable += 1
                    else: stable = 0
                    last = cur
                    if stable >= 2 and cur: break
                    time.sleep(3)
                emit({"ok": bool(last), "reply": (last or "")[:2000], "url": pg.url, "account": aid})

            box = find_box(pg, 7 if a.cmd != "send" else 10)

            if a.cmd == "status":
                body = "" if box else (pg.evaluate("()=>document.body.innerText") or "")
                wall = (not box) and ("登录" in body or "手机号" in body)
                emit({"ok": bool(box), "logged_in": bool(box), "login_wall": wall,
                      "url": pg.url, "account": aid, "proxy": bool(proxy),
                      "days_left": sess_days_left(auth) if auth else None})

            if a.cmd == "send":
                if a.new_chat:
                    new_chat(pg)
                n0 = pg.evaluate("""()=>document.querySelectorAll('[class*=message],[data-message],[role=listitem]').length""")
                marker = "[ISHII-" + uuid.uuid4().hex[:6] + "]"
                delivered = send_with_verify(pg, a.text, marker)
                n1 = pg.evaluate("""()=>document.querySelectorAll('[class*=message],[data-message],[role=listitem]').length""")
                try:
                    pg.screenshot(path=str(BASE / "out" / f"mcp_{marker[7:-1]}.png"))
                except Exception:
                    pass
                emit({"ok": delivered, "marker": marker, "delivered": delivered,
                      "n_before": n0, "n_after": n1, "url": pg.url,
                      "account": aid, "proxy": bool(proxy), "new_chat": a.new_chat})

            emit({"ok": False, "error": "COMPOSER_NOT_FOUND (未登录或页面未就绪)", "url": pg.url})
        finally:
            ctx.close()

if __name__ == "__main__":
    main()
