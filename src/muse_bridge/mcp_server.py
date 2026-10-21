#!/usr/bin/env python3
"""MCP Server v2 — Muse 云端智能体桥 (muse-bridge)
多账号 + 代理分散 + 可迁移认证包 + 稳定性加固。
工具:
  muse_send(prompt, account?, new_chat?)   下发任务（输入框校验+重试，唯一标记硬证送达）
  muse_poll(timeout_s?, account?)          取回最新回复
  muse_status(account?)                    登录态/代理/会话剩余天数
  muse_accounts()                          列出全部账号（id/代理/剩余天数/默认）
  muse_export(account?)                    刷新该账号可移植认证包 auth.json
协议: stdio JSON-RPC（与 ui_hand_mcp_server.py 同族，零依赖）。
"""
import sys, os, json, asyncio, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(BASE)            # src/：子进程按包名 import muse_bridge.* 需要它在 PYTHONPATH
WORKER = os.path.join(BASE, "worker.py")
ACCOUNTS = os.path.join(BASE, "accounts.py")
POOL = os.path.join(BASE, "pool.py")
CRED_BUNDLE = os.path.join(BASE, "cred_bundle.py")

def _env():
    e = dict(os.environ)
    e["PYTHONPATH"] = SRC + os.pathsep + e.get("PYTHONPATH", "")
    return e

def _pick_py():
    cand = [os.environ.get("MUSE_PY"),
            "",
            sys.executable]
    for c in cand:
        if c and os.path.exists(c):
            try:
                r = subprocess.run([c, "-c", "import playwright"], capture_output=True, timeout=20)
                if r.returncode == 0:
                    return c
            except Exception:
                continue
    return cand[1] if os.path.exists(cand[1]) else sys.executable
PY = _pick_py()

def respond(msg_id, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": msg_id}
    if error:
        payload["error"] = error
    else:
        payload["result"] = result
    print(json.dumps(payload), flush=True)

def run(cmd_args, timeout=300):
    """cmd_args[0]=脚本路径, 其余=参数。统一 -X utf8 + JSON 行扫描。"""
    try:
        r = subprocess.run([PY, "-X", "utf8"] + cmd_args, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace", env=_env())
        out = (r.stdout or "").strip().splitlines()
        for ln in reversed(out):
            ln = ln.strip()
            if ln.startswith("{"):
                try: return json.loads(ln)
                except json.JSONDecodeError: continue
        return {"ok": False, "error": "no json from worker; stderr: " + (r.stderr or "")[-300:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"worker timeout {timeout}s"}

ACC_PROP = {"account": {"type": "string",
    "description": "账号 id（accounts/registry.json）。缺省=registry.default；\"pool\"=自动选路（健康度最优、失败冷却避让）。示例: muse-default"}}

TOOLS = [
    {"name": "muse_send",
     "description": "向云端 Muse 智能体(muse.ai)下发任务。复用浏览器登录态，headless 注入 composer 并回车；输入框校验+重试，唯一 ISHII 标记硬证送达。多账号：传 account 选号分散额度。返回 {ok, marker, delivered, account, proxy, url}。",
     "inputSchema": {"type": "object", "properties": {
         "prompt": {"type": "string", "description": "要下达给 Muse 的任务/消息文本"},
         "new_chat": {"type": "boolean", "description": "先开新会话再发（缺省 false）"},
         "account": ACC_PROP["account"]},
         "required": ["prompt"]}},
    {"name": "muse_poll",
     "description": "轮询取回 Muse 最新助手回复文本（等待稳定）。返回 {ok, reply, account}。",
     "inputSchema": {"type": "object", "properties": {
         "timeout_s": {"type": "integer", "description": "最长等待秒数，缺省 120"},
         "account": ACC_PROP["account"]}}},
    {"name": "muse_status",
     "description": "检查账号登录态与页面健康：composer 存在性、登录墙、代理是否生效、会话剩余天数。返回 {ok, logged_in, login_wall, days_left, proxy}。",
     "inputSchema": {"type": "object", "properties": {
         "account": ACC_PROP["account"]}}},
    {"name": "muse_accounts",
     "description": "列出全部 Muse 账号（id/label/是否代理/会话剩余天数/默认号）。用于多账号调度选路与额度分散。",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "muse_export",
     "description": "刷新账号的可移植认证包 accounts/<id>/auth.json（Playwright storage_state 格式）。拷走 auth.json 即可在任何装有本桥+Chromium 的机器 import 复现登录态——迁移单元。",
     "inputSchema": {"type": "object", "properties": {
         "account": ACC_PROP["account"]}}},
    {"name": "muse_pool",
     "description": "凭证池调度（中转站式多账号管理）。status=各号健康度(days_left/连续失败/今日用量/可用)；next=按策略选下一个账号(失败少→剩余天数多→最久未用)；use=回报某号本次结果(ok/fail，失败进冷却避让)；reset=清零失败计数(重登/保鲜后)。返回 JSON。",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["status", "next", "use", "reset"], "description": "池操作"},
         "account": ACC_PROP["account"],
         "result": {"type": "string", "enum": ["ok", "fail"], "description": "action=use 时的本次结果，缺省 ok"}},
         "required": ["action"]}},
    {"name": "muse_cred",
     "description": "凭证包管理（跨机同步/备份）。pack=把账号凭证打包成标准 tar.gz（manifest+registry+auth，带 sha256）；unpack=在目标机加载凭证包并合并 registry（可 verify 纯凭证有效性）；inspect=只读查看包内容。auth.json 等同账号密码，包文件勿入 git、传输走可信通道。",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["pack", "unpack", "inspect"], "description": "凭证包操作"},
         "path": {"type": "string", "description": "包文件路径（pack 输出 / unpack·inspect 输入）"},
         "accounts": {"type": "string", "description": "action=pack 限定账号 id，逗号分隔；缺省全部"},
         "verify": {"type": "boolean", "description": "action=unpack 时逐一纯凭证验证（推荐）"}},
         "required": ["action", "path"]}},
]

async def handle_stdio():
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {})
        if method == "initialize":
            respond(msg_id, {"protocolVersion": "2024-11-05",
                             "capabilities": {"tools": {"listChanged": False}},
                             "serverInfo": {"name": "muse-bridge", "version": "2.0.0"}})
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            respond(msg_id, {"tools": TOOLS})
        elif method == "tools/call":
            name = params.get("name"); args = params.get("arguments", {})
            acc = ["--account", args["account"]] if args.get("account") else []
            if name == "muse_send":
                wargs = [WORKER, "send", args.get("prompt", "")] + acc
                if args.get("new_chat"): wargs.append("--new-chat")
                res = run(wargs, timeout=380)
            elif name == "muse_poll":
                res = run([WORKER, "poll", "--timeout", str(args.get("timeout_s", 120))] + acc, timeout=300)
            elif name == "muse_status":
                res = run([WORKER, "status"] + acc, timeout=150)
            elif name == "muse_accounts":
                res = run([WORKER, "accounts"], timeout=60)
            elif name == "muse_export":
                res = run([ACCOUNTS, "export", args.get("account") or "muse-default"], timeout=200)
            elif name == "muse_pool":
                act = args.get("action", "status")
                pargs = [POOL, act]
                if args.get("account"):
                    pargs.append(args["account"])
                if act == "use":
                    pargs.append("--" + (args.get("result") or "ok"))
                res = run(pargs, timeout=60)
            elif name == "muse_cred":
                act = args.get("action", "inspect")
                cargs = [os.path.join(BASE, "cred_bundle.py"), act, args.get("path", "")]
                if act == "pack" and args.get("accounts"):
                    cargs += ["--accounts", args["accounts"]]
                if act == "unpack" and args.get("verify"):
                    cargs.append("--verify")
                res = run(cargs, timeout=300)
            else:
                res = {"ok": False, "error": f"unknown tool {name}"}
            respond(msg_id, {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}],
                             "isError": not res.get("ok", False)})
        elif method in ("ping",):
            respond(msg_id, {})
        elif msg_id is not None:
            respond(msg_id, error={"code": -32601, "message": f"method {method} not found"})

if __name__ == "__main__":
    try:
        asyncio.run(handle_stdio())
    except (KeyboardInterrupt, BrokenPipeError):
        pass
