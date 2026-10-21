# -*- coding: utf-8 -*-
"""probe_login_step2.py — 登录墙第二步探测：填占位手机号→点继续→dump 下一步表单结构。
不提交真实账号，只评估页面流（密码步/验证码步/OAuth 步）。"""
import os, json, time
from pathlib import Path

BASE = Path(os.environ.get("MUSE_HOME", str(Path(__file__).resolve().parents[1])))
CHROME = os.environ.get("MUSE_CHROME") or None
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")
PROF = str(BASE / "out" / "probe-empty-profile")

Path(PROF).mkdir(parents=True, exist_ok=True)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROF, executable_path=CHROME, headless=True,
        args=["--headless=new", "--disable-gpu", "--no-first-run", "--window-size=1280,900"],
        ignore_default_args=["--enable-automation"], locale="zh-CN", user_agent=UA)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto("https://muse.ai", wait_until="domcontentloaded", timeout=60000)
    time.sleep(5)
    info = {"steps": []}
    # step1: 填占位手机号 + 点继续（占位号不会真的发送任何东西）
    try:
        box = pg.query_selector("input[aria-label='手机号或邮箱']") or pg.query_selector("input[type=text]")
        if box:
            box.click(); box.fill("+15550001234")
            time.sleep(1)
            for b in pg.query_selector_all("button"):
                if "继续" in (b.inner_text() or ""):
                    b.click(); break
            time.sleep(6)
    except Exception as e:
        info["step1_err"] = str(e)[:120]
    snap = pg.evaluate("""() => {
      const pick = (el) => ({tag: el.tagName, type: el.type||null, aria: el.getAttribute('aria-label'),
        placeholder: el.placeholder||null, autocomplete: el.getAttribute('autocomplete'),
        text: (el.innerText||'').slice(0,30), visible: !!(el.offsetWidth||el.offsetHeight)});
      return {url: location.href,
        inputs: [...document.querySelectorAll('input')].map(pick),
        buttons: [...document.querySelectorAll('button,[role=button]')].slice(0,12).map(pick),
        bodyText: (document.body?document.body.innerText:'').slice(0,400)};
    }""")
    info["steps"].append({"after_continue": snap})
    try:
        pg.screenshot(path=str(BASE / "out" / "login_step2.png"), full_page=True)
    except Exception:
        pass
    ctx.close()
print(json.dumps(info, ensure_ascii=False, indent=1))
