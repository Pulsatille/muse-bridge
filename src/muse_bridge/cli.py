"""Muse 命令下发·生产验证：headless 复用已登录 profile，唯一标记法确认真的送达。
用法: python muse_cmd.py "任务文本"    (缺省冒烟)
输出: JSON{ok, marker_found, session_url, n_messages_after, screenshot}
"""
import sys, time, json, uuid, os
from pathlib import Path
from playwright.sync_api import sync_playwright

CHROME_EXE = os.environ.get("MUSE_CHROME") or None
BASE = Path(os.environ.get("MUSE_HOME", str(Path(__file__).resolve().parents[2])))
PROFILE = str(BASE / "chrome-full")
OUT = BASE / "out"

PROMPT = sys.argv[1] if len(sys.argv) > 1 else "工作状态自检"
MARK = "[ISHII-" + uuid.uuid4().hex[:6] + "]"
FULL = f"{MARK} {PROMPT}"

def msg_count(pg):
    return pg.evaluate("""() => document.querySelectorAll('[class*=message],[data-message],[role=listitem]').length""")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE, executable_path=CHROME_EXE, headless=True,
        args=["--headless=new", "--disable-gpu", "--no-first-run", "--window-size=1280,900"],
        ignore_default_args=["--enable-automation"], locale="zh-CN",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto("https://muse.ai", wait_until="domcontentloaded", timeout=60000)
    box = None
    for _ in range(10):
        time.sleep(3)
        box = pg.query_selector("textarea[placeholder*='消息']") or pg.query_selector("textarea")
        if box: break
    if not box:
        pg.screenshot(path=str(OUT / "cmd_fail.png"), full_page=True)
        print(json.dumps({"ok": False, "error": "COMPOSER_NOT_FOUND"})); ctx.close(); sys.exit(2)

    n0 = msg_count(pg)
    box.click(); time.sleep(0.4)
    pg.keyboard.type(FULL, delay=12); time.sleep(0.5)
    pg.keyboard.press("Enter")
    print("[SENT]", FULL)

    # 轮询：标记出现在页面 = 已投递；再等助手开始响应（消息数增加/出现"停止"按钮）
    delivered, replied = False, False
    deadline = time.time() + 150
    while time.time() < deadline:
        time.sleep(4)
        body = pg.evaluate("()=>document.body.innerText")
        if not delivered and MARK in body:
            delivered = True
            print("[DELIVERED] marker visible in session")
        if delivered and msg_count(pg) > n0 + 1:
            replied = True
            break
    pg.screenshot(path=str(OUT / "cmd_result.png"), full_page=True)
    res = {"ok": delivered, "marker": MARK, "delivered": delivered, "assistant_replied": replied,
           "n_before": n0, "n_after": msg_count(pg), "url": pg.url,
           "screenshot": str(OUT / "cmd_result.png")}
    (OUT / "cmd_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False))
    ctx.close()
    sys.exit(0 if delivered else 3)
