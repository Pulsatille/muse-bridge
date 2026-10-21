# -*- coding: utf-8 -*-
"""probe_login_wall.py — 用空 profile 打开 Muse，dump 登录墙的 DOM 结构（输入框/按钮/选择器），
评估自动填写账号密码的可行性。只读侦察，不提交任何数据。"""
import os, json, time
from pathlib import Path

BASE = Path(os.environ.get("MUSE_HOME", str(Path(__file__).resolve().parents[1])))
CHROME = os.environ.get("MUSE_CHROME") or None
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")
EMPTY_PROF = str(BASE / "out" / "probe-empty-profile")
SHOT = str(BASE / "out" / "login_wall_probe.png")

Path(EMPTY_PROF).mkdir(parents=True, exist_ok=True)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=EMPTY_PROF, executable_path=CHROME, headless=True,
        args=["--headless=new", "--disable-gpu", "--no-first-run", "--window-size=1280,900"],
        ignore_default_args=["--enable-automation"], locale="zh-CN", user_agent=UA)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        pg.goto("https://muse.ai", wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print("goto err:", str(e)[:120])
    time.sleep(6)
    # dump 所有 input / button / textarea 与 iframe
    info = pg.evaluate("""() => {
      const pick = (el) => ({
        tag: el.tagName, type: el.type||null, name: el.name||null,
        id: el.id||null, placeholder: el.placeholder||null,
        aria: el.getAttribute('aria-label'), autocomplete: el.getAttribute('autocomplete'),
        text: (el.innerText||'').slice(0,40), visible: !!(el.offsetWidth||el.offsetHeight)
      });
      return {
        url: location.href,
        inputs: [...document.querySelectorAll('input')].map(pick),
        buttons: [...document.querySelectorAll('button,[role=button]')].slice(0,15).map(pick),
        textareas: [...document.querySelectorAll('textarea')].map(pick),
        iframes: [...document.querySelectorAll('iframe')].map(f=>({src:(f.src||'').slice(0,120), id:f.id})),
        bodyText: (document.body?document.body.innerText:'').slice(0,600)
      };
    }""")
    try:
        pg.screenshot(path=SHOT, full_page=True)
        info["screenshot"] = SHOT
    except Exception as e:
        info["shot_err"] = str(e)[:100]
    ctx.close()
print(json.dumps(info, ensure_ascii=False, indent=1))
