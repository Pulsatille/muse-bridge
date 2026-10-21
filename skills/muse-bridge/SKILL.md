---
name: muse-bridge
description: "让本地 AI 智能体通过浏览器 DOM 桥命令云端 Muse (muse.ai)：下发任务、取回回复、多账号管理、代理分散、可移植认证包。含 MCP 工具 muse_send/muse_poll/muse_status/muse_accounts/muse_export 与 CLI 用法。"
version: 1.0.0
author: muse-bridge contributors
license: MIT
platforms: [windows, linux]
metadata:
  hermes:
    tags: [muse, ai-agent, browser, playwright, mcp, dom-bridge, automation]
    related_skills: [muse_accounts, playwright-mcp]
prerequisites:
  commands: [python, playwright]
  env:
    - MUSE_HOME (可选，默认发布包根目录)
    - MUSE_CHROME (可选，Chromium 可执行文件路径)
    - MUSE_PY (可选，带 playwright 的 Python 解释器路径)
    - MUSE_ACCOUNT (可选，默认账号 id)
---

# muse-bridge — 命令云端 Muse

`muse-bridge` 让本地 AI 智能体（Hermes Agent / 任意 MCP 客户端）通过**浏览器 DOM 桥**操作云端 **Muse**（muse.ai 网页 AI）。它复用你自己的浏览器登录态（Playwright 持久上下文），headless 注入 composer 并取回真实回复。**不含 Muse 官方 API**，只操作你有权使用的自有账号。

## 一、安装与配置

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 环境变量

| 变量 | 用途 | 缺省 |
|------|------|------|
| `MUSE_HOME` | 数据根目录（accounts/registry.json、各号 profile/auth.json） | 发布包根目录 |
| `MUSE_CHROME` | Chromium 可执行文件路径 | 自动探测 Playwright 缓存 |
| `MUSE_PY` | 带 playwright 的 Python 解释器路径 | 自动探测 |
| `MUSE_ACCOUNT` | 默认账号 id | registry.default |
| `MUSE_DEFAULT_ACCOUNT` | accounts.py 新建注册表时的默认账号名 | muse-default |

### 账号准备（一次性）

```bash
# 方式 A：已有登录态（storage_state）可移植导入
python -m muse_bridge.accounts import muse-default --auth /path/to/auth.json

# 方式 B：用 CLI 打开登录辅助（需人工完成 Muse 登录后自动导出 auth.json）
python -m muse_bridge.cli login

# 查看账号
python -m muse_bridge.accounts list
```

## 二、MCP 工具（推荐给智能体使用）

通过 `python -m muse_bridge.mcp_server` 启动 stdio MCP 服务器，暴露 7 个工具：

| 工具 | 参数 | 返回关键字段 | 用途 |
|------|------|--------------|------|
| `muse_send` | `prompt`(必填), `new_chat`?, `account`? | ok/marker/delivered/account/proxy/url | 下发任务，唯一标记硬证送达 |
| `muse_poll` | `timeout_s`?, `account`? | ok/reply/account | 轮询取回最新助手回复 |
| `muse_status` | `account`? | ok/logged_in/login_wall/days_left/proxy | 检查登录态与会话健康 |
| `muse_accounts` | — | accounts[]（id/label/proxy/days_left/default） | 列出全部账号 |
| `muse_export` | `account`? | ok/auth | 刷新可移植认证包 auth.json |
| `muse_pool` | `action`(必填 status/next/use/reset), `account`?, `result`? | pool[]（days_left/fails/cooling/usable/today_uses）或 {account,reason} | 凭证池调度：健康度评分 + 自动选号 + 失败冷却避让 |
| `muse_cred` | `action`(必填 pack/unpack/inspect), `path`(必填), `accounts`?, `verify`? | ok/loaded/accounts[]/rejected[]/verify[] | 凭证包跨机同步：打包(带 sha256)/加载/查看 |

**`account` 取值**：具体账号 id ／ `pool`（自动选健康度最优号）。

**智能体调用规范**：
1. 需要 Muse 干活 → `muse_send(prompt="...", account="pool")`（不指定号则池自动选路）
2. 等它回话 → `muse_poll(timeout_s=120, account="pool")`
   （池是**粘性会话**：send 锁定的号会写入 `_active` 指针，poll/status 自动沿用同一个号，
   所以 send 与 poll 都用 `account="pool"` 即可，无需自己记账号）
3. 事前检查可用号 → `muse_pool(action="status")` 看 usable/days_left/cooling
4. 某号连续失败 2 次会进 1h 冷却自动避让；重登或保鲜后 → `muse_pool(action="reset", account=<id>)`
5. 认证快过期（days_left < 7）→ 提醒主人重新登录，或 `muse_export` 保鲜
6. 跨机同步整套凭证 → `muse_cred(action="pack", path="pool.tar.gz")`，
   把文件传到目标机后 `muse_cred(action="unpack", path=..., verify=true)`
   （profile 缺失时池会自愈：自动用 auth.json 灌入）

## 三、CLI 用法（不经 MCP 的快捷通道）

```bash
# 下发任务（独立派遣）
python -m muse_bridge.cli "帮我查一下今天的新闻"

# 指定账号下发（worker 直接调用）
python -X utf8 -m muse_bridge.worker send "任务文本" --account muse-main
python -X utf8 -m muse_bridge.worker poll --timeout 120 --account muse-main
python -X utf8 -m muse_bridge.worker status --account muse-main

# 多账号
python -X utf8 -m muse_bridge.accounts list
python -X utf8 -m muse_bridge.accounts export muse-main
python -X utf8 -m muse_bridge.accounts import muse-main --auth /path/auth.json
python -X utf8 -m muse_bridge.accounts setproxy muse-main socks5://user:pass@host:1080
```

## 四、排障

| 现象 | 原因 | 处置 |
|------|------|------|
| `muse_status` 返回 `login_wall: true` | profile 浏览器会话被 Muse 登出 | 用 `muse_login2`/`cli login` 重新登录，或 `accounts import` 注入有效 auth.json |
| `muse_send` 返回 `delivered: false, n_before: 0` | 页面未渲染消息区（会话失效/登录墙） | 先 `muse_status` 确认，再重新登录 |
| `days_left: null` | auth.json 缺失或格式不对 | `accounts export` 重新生成认证包 |
| 打开浏览器报错 | Chromium 未安装或路径不对 | 设置 `MUSE_CHROME` 指向真实 chromium，或 `python -m playwright install chromium` |
| Linux 缺系统库 | headless 依赖不全 | 按 `docs/INSTALL.md` 安装 libnss3/libgbm1 等 |

## 五、红线（必须遵守）

1. **只操作自有账号**：本项目仅用于你有权使用的 Muse 账号，遵守 muse.ai 服务条款。
2. **auth.json 等同账号密码**：storage_state 含完整登录态，泄露即等于账号泄露，**绝不提交 git**。
3. **不读取无关数据**：只操作 Muse 聊天页 DOM，不碰浏览器历史/书签/其他网站数据。
4. **代理合规**：多账号分散代理时，不得用于绕过平台风控之外的非法用途。