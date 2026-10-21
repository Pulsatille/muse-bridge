# muse-bridge

让本地 AI 智能体（Hermes Agent / 任意 MCP 客户端）通过浏览器 DOM 桥**命令云端 Muse**（muse.ai 网页 AI），并取回真实回复。多账号、代理分散、可移植认证包。

> 公益开源项目。本项目不含 Muse 官方 API —— 走的是你自己的浏览器登录态（Playwright DOM），**仅用于操作你有权使用的自有账号**。使用前请阅读 `docs/DISCLAIMER.md`。

设计取舍见 [DESIGN.md](DESIGN.md)，组件/数据结构见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 它给谁用？怎么用？

**面向的智能体**：任何支持 **MCP（Model Context Protocol）** 的本地 AI 智能体，最典型的是：

- **Hermes Agent**（v0.13.0+，本项目的原生适配对象）
- Claude Code / Codex / Cursor / OpenClaw 等任意 MCP 客户端

**一句话用法**：把你的 Muse 账号登录态交给它，然后对它说「用 Muse 帮我做 XX」，它会自动：

1. 调用 `muse_send` 把你的任务下发到云端 Muse 网页聊天框
2. 调用 `muse_poll` 轮询取回 Muse 的真实回复
3. 用 `muse_status` / `muse_accounts` 检查账号健康、切换账号、分散额度

**本机 Hermes 完整接入步骤**（详细版见 `docs/INSTALL.md`）：

```bash
# 1) 安装依赖
pip install -r requirements.txt
python -m playwright install chromium

# 2) 准备账号（登录态）
python -m muse_bridge.accounts import muse-default --auth /path/to/auth.json
#    或首次登录：python -m muse_bridge.cli login

# 3) 注册为 Hermes 的 MCP 服务器（编辑 ~/.hermes/config.yaml）
#    mcp_servers:
#      muse-bridge:
#        command: python
#        args: ["-X", "utf8", "-m", "muse_bridge.mcp_server"]
#        cwd: "/path/to/muse-bridge/src"

# 4) 验证
hermes mcp test muse-bridge   # 应看到 5 个工具
```

**Hermes 技能文件**：仓库自带 `skills/muse-bridge/SKILL.md`，安装后 Hermes 会学会自己调用这些工具：

```bash
mkdir -p ~/.hermes/skills/muse-bridge
copy skills\muse-bridge\SKILL.md ~\.hermes\skills\muse-bridge\SKILL.md
```

## 特性

- **MCP stdio 服务器**：`muse_send / muse_poll / muse_status / muse_accounts / muse_export` 五个工具，零第三方依赖
- **浏览器 DOM 桥**：Playwright 持久上下文 + 真实登录态（`storage_state`），headless 注入 composer、校验输入框、唯一标记硬证送达
- **多账号**：`registry.json` 集中管理（profile + 代理 + 可移植认证包），按号分散额度
- **可迁移认证包**：`auth.json`（Playwright storage_state）拷走即可在另一台机器 import 复现登录态

## 快速开始

```powershell
# 0) 一键安装（venv + 依赖 + Chromium + 自检）
python install.py
#    不装浏览器：python install.py --skip-browser

# 2) 登录一个 Muse 账号（一次性，生成 accounts/muse-default/auth.json）
python -m muse_bridge.cli login

# 3) 启动 MCP 服务器（任意 MCP 客户端连它即可）
python -m muse_bridge.mcp_server
```

或直接命令行派遣（不经 MCP）：

```powershell
python -m muse_bridge.cli "帮我查一下今天的新闻"
python -m muse_bridge.worker status
python -m muse_bridge.accounts list
```

## 环境变量

| 变量 | 用途 |
|------|------|
| `MUSE_HOME` | 数据根目录（默认 `~/.hermes-muse-bridge`），存放 accounts/registry.json 与各号 profile/auth.json |
| `MUSE_PY` | 带 playwright 的 Python 解释器路径（默认自动探测） |
| `MUSE_CHROME` | Chromium 可执行文件路径（默认自动探测 Playwright 缓存） |
| `MUSE_DEFAULT_ACCOUNT` | 缺省账号 id（默认由 registry.default 决定） |
| `MUSE_ACCOUNT` | worker 进程级默认账号 id |

## 目录结构

```
muse-bridge/
├── src/muse_bridge/       # 核心代码
│   ├── mcp_server.py      # MCP stdio 服务器（5 工具）
│   ├── worker.py          # Playwright DOM worker（send/poll/status/accounts）
│   ├── accounts.py        # 多账号注册表 CLI
│   └── cli.py             # 独立命令行派遣器
├── docs/                  # 安装/架构/免责声明
├── skills/                # Hermes 技能（SKILL.md）
├── tests/                 # 核心测试
├── run_me.py              # 一键装配/测试/打包
├── pyproject.toml
└── requirements.txt
```

## 测试

```powershell
python -m muse_bridge.accounts list   # 无账号也应正常输出空列表
python run_me.py --check                # 编译 + MCP 握手自检
python tests/test_core.py              # 3/3 核心测试
```

## 凭证提取与自动保活（多账号管理）

```bash
# 登录一次（弹可见浏览器，人工完成手机号/验证码），检测登录后自动提取凭证并登记 registry
python -m muse_bridge.cred_extract login muse-main

# 凭证摘要 / 纯凭证有效性验证（不依赖 profile，验证 auth.json 单独可用=无损迁移）
python -m muse_bridge.cred_extract list
python -m muse_bridge.cred_extract verify muse-main

# 保活：打开 muse.ai 确认登录态并重新导出 auth.json（hatch_sess 服务端滑动续期）
python -m muse_bridge.keepalive tick                 # 全部账号
# Hermes cron 已接入：muse-keepalive 每 6h 自动 tick，异常才输出（触发错误审计）
```

## 凭证池与多账号调度（中转站式）

登录一遍 → 凭证入池 → 池做选路/同步，多账号像中转站一样管理：

```bash
# 池视图：各号 days_left / 连续失败 / 今日用量 / 可用 / 冷却
python -m muse_bridge.pool status

# 自动选路（失败少→剩余天数多→最久未用）；worker 直接按池选号
python -m muse_bridge.pool next
python -m muse_bridge.worker send "任务" --account pool

# 全池凭证打包 → 拷到任意机器一条命令加载（sha256 校验 + 纯凭证验证）
python -m muse_bridge.cred_bundle pack cred_pool.tar.gz
python -m muse_bridge.cred_bundle inspect cred_pool.tar.gz
python -m muse_bridge.cred_bundle unpack cred_pool.tar.gz --merge --verify

# 重登/保鲜后清零失败计数
python -m muse_bridge.pool reset muse-main
```

MCP 同样暴露 `muse_pool` / `muse_cred` 两个工具；`muse_send(account="pool")` 即池选号。

> 自动填写说明：Muse 登录页无密码字段（手机号+验证码/Meta OAuth），因此本工具
> **不做**自动闯墙；正确路径是 `login` 人工一次 + `keepalive` 长期滑动保活。
> 内存实测：一次 tick 峰值 ~316MB，跑完即释放，24h 无常驻。

## 服务器部署（与本地共用凭证）

```bash
git clone https://github.com/Pulsatille/muse-bridge.git && cd muse-bridge
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
# 把本地 accounts/<id>/auth.json 拷到服务器同路径，然后导入：
PYTHONPATH=src MUSE_HOME=$PWD .venv/bin/python -m muse_bridge.cred_extract import muse-main
PYTHONPATH=src MUSE_HOME=$PWD .venv/bin/python -m muse_bridge.worker status --account muse-main
# 保活 cron（每 6h）：0 */6 * * * cd <repo> && PYTHONPATH=src MUSE_HOME=<repo> .venv/bin/python -m muse_bridge.keepalive tick
```

完整步骤见 `docs/INSTALL.md`；跨机路径由 registry `_resolve` 自愈（绝对路径失效按尾段重建）。

## 未来更新计划（Roadmap）

> **重要备注**：以下均为**未来计划，存在不确定性**，是否实现、以何种形态实现，取决于作者的实际实践与时间投入。**若社区中有任何人提前完成了其中某项，欢迎直接提交 PR / fork 后强行合并**（同一目标先到先得），作者不会以"这是我的计划"为由拒绝。

- **账号隔离（Account Isolation）**：将不同 Muse 账号的浏览器 profile、认证包、数据目录彻底隔离，互不读写，避免一个账号异常时污染其他账号。
- **账号地区切割（Geo Partitioning）**：按账号所属地区/时区分配不同代理出口与浏览器指纹（locale、时区、UA），降低多账号同机操作被风控关联的概率，从而**防止封号**。
- 其他待定：会话失效自动重登、配额用量统计、Muse 回复质量打分、多机同步等。

## 作者的话（项目理念）

> 我本人认为，一个大厂的产品，发布下来最好的解法并不是在于比谁可以抢夺更多的用户，而是在于谁能够更好地配合，来服务于我们的生活。正因如此，我强烈呼吁各厂商在做个人智能体时，最好把一些接口开放出来，能给本地的智能体进行相互兼容，来保证科技服务于生活，而不是服务于金钱。我之所以选择 Hermes，也仅仅是因为它可以在我的电脑上跑起来——比 OpenClaw 更轻、更顺。这个项目就是把这种「开放、互操作、科技服于人」的理念变成现实的一次尝试：云端 Muse 的接口没有开放，我们就用浏览器 DOM 桥把它打开。

更多：`docs/INSTALL.md`（服务器部署）、`docs/ARCHITECTURE.md`（接口/数据流）、`docs/DISCLAIMER.md`（免责声明）。作者原话修正与中英对照见 `AUTHOR_NOTES.md`。