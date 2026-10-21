#!/usr/bin/env python3
"""muse_accounts.py — Muse 多账号注册表 CLI（账号=profile+代理+认证包 三件套）
注册表: <MUSE_HOME>\\accounts\\registry.json
结构:
{
  "default": os.environ.get("MUSE_DEFAULT_ACCOUNT", "muse-default"),
  "accounts": {
    "muse-default": {
      "profile": "D:/.../accounts/muse-default/profile",   # 运行态浏览器 profile
      "auth":    "D:/.../accounts/muse-default/auth.json", # 可移植认证包(Playwright storage_state)
      "proxy":   null,                                   # "http://user:pass@host:port" 或 socks5://host:port
      "label":   "主号",
      "quota_note": "每周 10 亿 token"
    }
  }
}
子命令:
  list                          列出全部账号 + 会话剩余天数
  add <id> [--proxy P] [--label L] [--auth FILE] [--profile DIR]
  rm <id>
  export <id>                   从现 profile 导出认证包 auth.json
  import <id>                   把 auth.json 灌入新 profile（异机迁移复原）
  setproxy <id> <proxy|none>
"""
import sys, os, json, time, argparse
from pathlib import Path

BASE = Path(os.environ.get("MUSE_HOME", str(Path(__file__).resolve().parents[2])))
ACC_ROOT = BASE / "accounts"
REG = ACC_ROOT / "registry.json"
CHROME = os.environ.get("MUSE_CHROME") or None
LEGACY_PROFILE = str(BASE / "chrome-full")

def _resolve(p):
    """跨机迁移路径解析：相对路径以 BASE 展开；绝对路径若不存在（旧机器遗留），
    按尾段 accounts/... 或 chrome-full 在 BASE 下重建——保证 registry 拷到哪台机器都可用。"""
    if not p:
        return p
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

def load_reg():
    if REG.exists():
        return json.loads(REG.read_text(encoding="utf-8"))
    return {"default": os.environ.get("MUSE_DEFAULT_ACCOUNT", "muse-default"), "accounts": {}}

def save_reg(r):
    REG.parent.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

def sess_days_left(auth_path):
    try:
        d = json.loads(Path(auth_path).read_text(encoding="utf-8"))
        for c in d.get("cookies", []):
            if c["name"] == "hatch_sess" and c.get("expires", 0) > 0:
                return round((c["expires"] - time.time()) / 86400, 1)
    except Exception:
        pass
    return None

def _open(p, profile, proxy=None):
    kw = dict(user_data_dir=profile, executable_path=CHROME, headless=True,
              args=["--headless=new", "--disable-gpu", "--no-first-run"],
              ignore_default_args=["--enable-automation"], locale="zh-CN")
    if proxy:
        kw["proxy"] = {"server": proxy}
    return p.chromium.launch_persistent_context(**kw)

def cmd_list(a):
    r = load_reg()
    out = []
    for aid, cfg in r["accounts"].items():
        prof = _resolve(cfg.get("profile")); auth = _resolve(cfg.get("auth"))
        out.append({"id": aid, "label": cfg.get("label", ""), "default": aid == r.get("default"),
                    "proxy": cfg.get("proxy"), "days_left": sess_days_left(auth or ""),
                    "profile": prof, "auth": auth})
    print(json.dumps(out, ensure_ascii=False, indent=1))

def cmd_add(a):
    r = load_reg()
    d = ACC_ROOT / a.id
    prof = a.profile or str(d / "profile")
    auth = a.auth or str(d / "auth.json")
    if a.id in r["accounts"]:
        print(json.dumps({"ok": False, "error": f"account {a.id} exists"})); return 1
    r["accounts"][a.id] = {"profile": prof, "auth": auth, "proxy": a.proxy,
                           "label": a.label or a.id}
    if not r.get("default"):
        r["default"] = a.id
    save_reg(r)
    print(json.dumps({"ok": True, "id": a.id, "profile": prof, "auth": auth}))
    return 0

def cmd_rm(a):
    r = load_reg()
    if a.id not in r["accounts"]:
        print(json.dumps({"ok": False, "error": "not found"})); return 1
    del r["accounts"][a.id]
    if r.get("default") == a.id:
        r["default"] = next(iter(r["accounts"]), None)
    save_reg(r)
    print(json.dumps({"ok": True, "removed": a.id}))
    return 0

def cmd_export(a):
    r = load_reg()
    cfg = r["accounts"].get(a.id, {})
    prof = _resolve(cfg.get("profile")) or (LEGACY_PROFILE if a.id == "muse-main" or a.id == "muse-default" else None)
    auth = _resolve(cfg.get("auth")) or str(ACC_ROOT / a.id / "auth.json")
    if not prof or not Path(prof).exists():
        print(json.dumps({"ok": False, "error": f"profile missing for {a.id}"})); return 1
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _open(p, prof, cfg.get("proxy"))
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto("https://muse.ai", wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)  # 让 SPA 把 localStorage 写全
        Path(auth).parent.mkdir(parents=True, exist_ok=True)
        ctx.storage_state(path=auth)
        # 补全 expires：Playwright 把 session cookie 写成 0/-1，迁移后无法判有效期。
        # 用 profile 实际 cookie（含 expires）回填到 storage_state 的 cookie 条目。
        try:
            real = {}
            for c in ctx.cookies():
                real[c["name"]] = c
            sd = json.loads(Path(auth).read_text(encoding="utf-8"))
            for c in sd.get("cookies", []):
                rc = real.get(c["name"])
                if rc and not c.get("expires"):
                    exp = rc.get("expires") or 0
                    if exp > 0:
                        c["expires"] = exp
            Path(auth).write_text(json.dumps(sd, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        ctx.close()
    print(json.dumps({"ok": True, "auth": auth, "days_left": sess_days_left(auth)}))
    return 0

def cmd_import(a):
    """把认证包灌进 profile——新机器迁移的核心动作，免重新登录。"""
    r = load_reg()
    cfg = r["accounts"].get(a.id, {})
    prof = a.profile or cfg.get("profile") or str(ACC_ROOT / a.id / "profile")
    auth = a.auth or cfg.get("auth")
    if not auth or not Path(auth).exists():
        print(json.dumps({"ok": False, "error": f"auth package missing: {auth}"})); return 1
    d = json.loads(Path(auth).read_text(encoding="utf-8"))
    cookies = d.get("cookies", [])
    if not cookies:
        print(json.dumps({"ok": False, "error": "auth package has no cookies"})); return 1
    from playwright.sync_api import sync_playwright
    Path(prof).mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = _open(p, prof, cfg.get("proxy"))
        ctx.add_cookies(cookies)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto("https://muse.ai", wait_until="domcontentloaded", timeout=60000)
        box, tries = None, 0
        while tries < 8:
            box = pg.query_selector("textarea[placeholder*='消息']") or pg.query_selector("textarea")
            if box: break
            time.sleep(3); tries += 1
        # localStorage 一并注入（origins 段）
        try:
            for o in d.get("origins", []):
                if o.get("origin", "").endswith("muse.ai"):
                    pg.goto(o["origin"], wait_until="domcontentloaded", timeout=30000)
                    for kv in o.get("localStorage", []):
                        pg.evaluate("(kv)=>localStorage.setItem(kv.name, kv.value)", kv)
        except Exception:
            pass
        ctx.close()  # cookies+storage 落盘进 profile
    print(json.dumps({"ok": bool(box), "account": a.id, "profile": prof,
                      "cookies": len(cookies), "composer": bool(box),
                      "days_left": sess_days_left(auth)}))
    return 0 if box else 1

def cmd_setproxy(a):
    r = load_reg()
    if a.id not in r["accounts"]:
        print(json.dumps({"ok": False, "error": "not found"})); return 1
    r["accounts"][a.id]["proxy"] = None if a.proxy == "none" else a.proxy
    save_reg(r)
    print(json.dumps({"ok": True, "id": a.id, "proxy": r["accounts"][a.id]["proxy"]}))
    return 0

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    x = sub.add_parser("add"); x.add_argument("id"); x.add_argument("--proxy"); x.add_argument("--label"); x.add_argument("--auth"); x.add_argument("--profile")
    x = sub.add_parser("rm"); x.add_argument("id")
    x = sub.add_parser("export"); x.add_argument("id")
    x = sub.add_parser("import"); x.add_argument("id"); x.add_argument("--auth"); x.add_argument("--profile")
    x = sub.add_parser("setproxy"); x.add_argument("id"); x.add_argument("proxy")
    a = ap.parse_args()
    return {"list": cmd_list, "add": cmd_add, "rm": cmd_rm,
            "export": cmd_export, "import": cmd_import, "setproxy": cmd_setproxy}[a.cmd](a) or 0

if __name__ == "__main__":
    sys.exit(main())
