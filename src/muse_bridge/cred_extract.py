#!/usr/bin/env python3
"""cred_extract.py — Muse 登录凭证提取小工具（headed 登录 + 自动提取 + 多账号凭证管理）

子命令:
  login <id> [--profile DIR]    打开可见浏览器等你登录 Muse；检测到 composer 后自动提取凭证
                                → accounts/<id>/auth.json（storage_state + expires 回填）并注册进 registry
  extract <id> [--profile DIR]  从已有 profile 静默提取（headless，适合定时保鲜/自动化）
  list                          列出全部账号凭证摘要（cookie 数 / hatch_sess 有无 / 剩余天数）
  verify <id>                   用 auth.json 开一次性 context 验证凭证真实有效（不依赖 profile）
  show <id> [--secret]          查看凭证条目明细（默认打码；--secret 输出完整值，慎用）

凭证 = Playwright storage_state：cookies（expires 回填）+ origins(localStorage)，
拷 auth.json 到任意装有 muse-bridge 的机器 `accounts import` 即无损迁移。
"""
import sys, os, json, time, argparse
from pathlib import Path

BASE = Path(os.environ.get("MUSE_HOME", str(Path(__file__).resolve().parents[2])))
ACC_ROOT = BASE / "accounts"
REG = ACC_ROOT / "registry.json"
CHROME = os.environ.get("MUSE_CHROME") or None
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")
MUSE_URL = "https://muse.ai"
KEY_COOKIES = ("hatch_sess", "hatch_gw", "wd", "datr")

def load_reg():
    try:
        return json.loads(REG.read_text(encoding="utf-8"))
    except Exception:
        return {"default": None, "accounts": {}}

def save_reg(r):
    REG.parent.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

def _resolve(p):
    """跨机路径解析：相对→BASE 展开；绝对但不存在→按 accounts/… 或 chrome-full 尾段重建。"""
    if not p:
        return None
    q = Path(p)
    if not q.is_absolute():
        return str(BASE / q)
    if q.exists():
        return str(q)
    parts = q.parts
    for i, part in enumerate(parts):
        low = str(part).lower()
        if low == "accounts" and i + 1 < len(parts):
            return str(BASE.joinpath(*parts[i:]))
        if low == "chrome-full":
            return str(BASE / "chrome-full")
    return str(q)

def resolve_profile(aid, cli=None):
    if cli:
        return cli
    cfg = load_reg().get("accounts", {}).get(aid, {})
    return _resolve(cfg.get("profile")) or str(ACC_ROOT / aid / "profile")

def resolve_auth(aid, cli=None):
    if cli:
        return cli
    cfg = load_reg().get("accounts", {}).get(aid, {})
    return _resolve(cfg.get("auth")) or str(ACC_ROOT / aid / "auth.json")

def days_left(auth_path):
    try:
        d = json.loads(Path(auth_path).read_text(encoding="utf-8"))
        for c in d.get("cookies", []):
            if c["name"] == "hatch_sess" and (c.get("expires") or 0) > 0:
                return round((c["expires"] - time.time()) / 86400, 1)
    except Exception:
        pass
    return None

def wait_composer(pg, timeout_s=600, interval=3):
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            box = pg.query_selector("textarea[placeholder*='消息']") or pg.query_selector("textarea")
            if box:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False

def dump_state(ctx, auth_path):
    """storage_state 落盘 + 从真实 ctx.cookies() 回填 expires（Playwright 对 session cookie 写 0/-1）。"""
    real = {c["name"]: c for c in ctx.cookies()}
    Path(auth_path).parent.mkdir(parents=True, exist_ok=True)
    ctx.storage_state(path=auth_path)
    sd = json.loads(Path(auth_path).read_text(encoding="utf-8"))
    fixed = 0
    for c in sd.get("cookies", []):
        rc = real.get(c["name"])
        if rc and (not c.get("expires") or c.get("expires", 0) <= 0):
            exp = rc.get("expires") or 0
            if exp > 0:
                c["expires"] = exp
                fixed += 1
    Path(auth_path).write_text(json.dumps(sd, ensure_ascii=False, indent=2), encoding="utf-8")
    return sd, fixed

def register(aid, profile, auth, label=None):
    r = load_reg()
    e = r["accounts"].setdefault(aid, {})
    e["profile"] = profile
    e["auth"] = auth
    e.setdefault("proxy", None)
    e["label"] = label or e.get("label") or aid
    if not r.get("default"):
        r["default"] = aid
    save_reg(r)

def cmd_login(a):
    prof = resolve_profile(a.id, a.profile)
    Path(prof).mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=prof, executable_path=CHROME, headless=False,
            args=["--disable-gpu", "--no-first-run", "--window-size=1280,900"],
            ignore_default_args=["--enable-automation"], locale="zh-CN", user_agent=UA)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            pg.goto(MUSE_URL, wait_until="domcontentloaded", timeout=90000)
        except Exception:
            pass
        print("[WAIT] 浏览器窗口已打开——请手动登录 Muse（手机号/验证码），检测到登录态后自动提取凭证…", flush=True)
        if not wait_composer(pg, timeout_s=a.timeout):
            ctx.close()
            print(json.dumps({"ok": False, "error": "LOGIN_TIMEOUT 未检测到 composer（登录未完成或页面选择器变化）"}))
            return 1
        time.sleep(3)  # 等 SPA 把 localStorage 写全
        auth = resolve_auth(a.id)
        sd, fixed = dump_state(ctx, auth)
        ctx.close()
    register(a.id, prof, auth, a.label)
    hs = [c for c in sd.get("cookies", []) if c["name"] == "hatch_sess"]
    print(json.dumps({"ok": True, "id": a.id, "auth": auth, "profile": prof,
                      "cookies": len(sd.get("cookies", [])), "expires_fixed": fixed,
                      "localStorage": sum(len(o.get("localStorage", [])) for o in sd.get("origins", [])),
                      "hatch_sess": bool(hs), "days_left": days_left(auth),
                      "key_names": [c["name"] for c in sd.get("cookies", []) if c["name"] in KEY_COOKIES]},
                     ensure_ascii=False))
    return 0

def cmd_extract(a):
    prof = resolve_profile(a.id, a.profile)
    if not prof or not Path(prof).exists():
        print(json.dumps({"ok": False, "error": f"profile missing: {prof}"})); return 1
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=prof, executable_path=CHROME, headless=True,
            args=["--headless=new", "--disable-gpu", "--no-first-run"],
            ignore_default_args=["--enable-automation"], locale="zh-CN", user_agent=UA)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            pg.goto(MUSE_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        time.sleep(4)
        auth = resolve_auth(a.id)
        sd, fixed = dump_state(ctx, auth)
        ctx.close()
    register(a.id, prof, auth)
    print(json.dumps({"ok": True, "id": a.id, "auth": auth, "cookies": len(sd.get("cookies", [])),
                      "expires_fixed": fixed, "days_left": days_left(auth)}, ensure_ascii=False))
    return 0

def cmd_list(a):
    r = load_reg()
    out = []
    for aid, cfg in r.get("accounts", {}).items():
        auth = _resolve(cfg.get("auth"))
        info = {"id": aid, "label": cfg.get("label", ""), "default": aid == r.get("default"),
                "proxy": bool(cfg.get("proxy")), "has_auth": bool(auth and Path(auth).exists()),
                "days_left": days_left(auth) if auth else None}
        if info["has_auth"]:
            try:
                sd = json.loads(Path(auth).read_text(encoding="utf-8"))
                info["cookies"] = len(sd.get("cookies", []))
                info["hatch_sess"] = any(c["name"] == "hatch_sess" for c in sd.get("cookies", []))
                info["localStorage"] = sum(len(o.get("localStorage", [])) for o in sd.get("origins", []))
                info["mtime"] = time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(auth)))
            except Exception as e:
                info["auth_error"] = str(e)[:80]
        out.append(info)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0

def cmd_verify(a):
    """纯凭证验证：auth.json → 一次性 context（不碰 profile），看 composer 是否出现。"""
    auth = _resolve(resolve_auth(a.id))
    if not auth or not Path(auth).exists():
        print(json.dumps({"ok": False, "error": f"auth missing: {auth}"})); return 1
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, executable_path=CHROME,
                              args=["--headless=new", "--disable-gpu"])
        ctx = b.new_context(storage_state=auth, locale="zh-CN", user_agent=UA)
        pg = ctx.new_page()
        try:
            pg.goto(MUSE_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        ok = wait_composer(pg, timeout_s=a.timeout, interval=3)
        url = pg.url
        ctx.close(); b.close()
    print(json.dumps({"ok": ok, "credential_valid": ok, "account": a.id, "url": url,
                      "days_left": days_left(auth)}, ensure_ascii=False))
    return 0 if ok else 1

def cmd_show(a):
    auth = _resolve(resolve_auth(a.id))
    if not auth or not Path(auth).exists():
        print(json.dumps({"ok": False, "error": f"auth missing: {auth}"})); return 1
    sd = json.loads(Path(auth).read_text(encoding="utf-8"))
    rows = []
    for c in sd.get("cookies", []):
        v = c.get("value", "")
        rows.append({"name": c["name"], "domain": c.get("domain", ""),
                     "value": v if a.secret else (v[:8] + "***" if len(v) > 8 else "***"),
                     "expires": c.get("expires") or 0,
                     "days_left": round((c.get("expires", 0) - time.time()) / 86400, 1) if c.get("expires", 0) > 0 else None})
    print(json.dumps({"ok": True, "account": a.id, "auth": auth, "cookies": rows,
                      "origins": [{"origin": o["origin"], "keys": [kv["name"] for kv in o.get("localStorage", [])]}
                                  for o in sd.get("origins", [])]}, ensure_ascii=False, indent=1))
    return 0

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("login"); x.add_argument("id"); x.add_argument("--profile"); x.add_argument("--label"); x.add_argument("--timeout", type=int, default=900)
    x = sub.add_parser("extract"); x.add_argument("id"); x.add_argument("--profile")
    sub.add_parser("list")
    x = sub.add_parser("verify"); x.add_argument("id"); x.add_argument("--timeout", type=int, default=60)
    x = sub.add_parser("show"); x.add_argument("id"); x.add_argument("--secret", action="store_true")
    a = ap.parse_args()
    return {"login": cmd_login, "extract": cmd_extract, "list": cmd_list,
            "verify": cmd_verify, "show": cmd_show}[a.cmd](a) or 0

if __name__ == "__main__":
    sys.exit(main())
