# Design

muse-bridge 把本地 AI 智能体接到**用户自己的 Muse 网页会话**上。它不做官方 API
逆向，也不托管账号；桥的是浏览器里的真实登录态和 DOM。

## 目标

- 任何 MCP 客户端（Hermes、Claude Code、Codex、Cursor 等）都能用
  `muse_send / muse_poll / muse_status / muse_accounts / muse_export` 五个工具。
- 一次安装、可迁移、可自检：`install.py` 建 venv、装依赖/Chromium、跑
  `run_me.py --check`。
- 多账号隔离：每号独立 profile、独立代理、独立可移植 `auth.json`。
- 凭证可提取、可管理、可自动保活，跨机无损迁移。

## 非目标

- 不绕过 Muse 的额度、风控或登录限制；不批量注册账号；**不自动获取短信/邮件验证码**
  （那是风控绕过，属红线）。
- 不读取浏览器历史/书签/无关页面；只操作 Muse 聊天页 DOM。
- 不做多租户/公网服务；这是本机单用户桥。
- 不把 `auth.json` 或 `accounts/` 放进 git。

## 组件

| 文件 | 职责 |
|---|---|
| `src/muse_bridge/mcp_server.py` | stdio JSON-RPC 协议层；`initialize`/`tools/list`/`tools/call`；零第三方依赖 |
| `src/muse_bridge/worker.py` | 执行层；Playwright 持久上下文、DOM 注入、投递校验、回复轮询 |
| `src/muse_bridge/accounts.py` | 账号注册表 + profile/auth/proxy 三件套 + 导入导出 + 跨机路径解析 `_resolve` |
| `src/muse_bridge/cli.py` | 首次登录与生产冒烟脚本 |
| `src/muse_bridge/cred_extract.py` | 凭证提取/管理小工具：`login`(headed 登录→自动提取) `extract`(headless 静默提取) `list`(凭证摘要) `verify`(纯凭证一次性验证) `show`(明细，默认打码) |
| `src/muse_bridge/keepalive.py` | 自动保活：逐号打开 muse.ai 确认登录态→`storage_state` 重新导出，滑动续期 hatch_sess |
| `scripts/probe_login_wall.py` | 登录墙 DOM 侦察（输入框/按钮/选择器 dump），评估自动填写可行性 |
| `scripts/probe_login_step2.py` | 登录第二步表单结构探测（只读侦察，不提交真实数据） |
| `run_me.py` | 自检：py_compile 核心模块 + MCP initialize 握手 + 可选 wheel 构建 |
| `install.py` / `install.sh` | 跨平台一键安装（venv + 依赖 + Chromium + 自检） |
| `tests/test_core.py` | 无网络、无登录的协议/账号层测试 |
| `.github/workflows/ci.yml` | Python 3.10–3.12 自检 + 测试 + installer dry-run |

## 数据流

```
MCP client
  │ stdio JSON-RPC
  ▼
mcp_server.py ──subprocess（-X utf8, JSON 行）──► worker.py
                                                   │ Playwright CDP
                                                   ▼
                                        Chromium（持久 profile）
                                                   │ DOM 注入 + Enter
                                                   ▼
                                             muse.ai composer
                                                   │ 回复 DOM 变化
                                                   ▼
                                             poll → JSON

保活环（无 MCP 参与，独立 cron）：
keepalive.tick ──► 打开 profile → muse.ai → 确认 composer
                        └─ dump_state(ctx) 回填 expires → 刷新 accounts/<id>/auth.json
                              （hatch_sess 服务端滑动续期，days_left 回升）
```

详细的数据结构与工具返回字段见 `docs/ARCHITECTURE.md`。

## 凭证生命周期（Credential Lifecycle）

```
 cred_extract login <id>          # 用户手动登录一次（手机号/验证码）
        │  检测到 composer → dump_state：storage_state + 真实 ctx.cookies() 回填 expires
        ▼
 accounts/<id>/auth.json  +  accounts/<id>/profile（运行态）  +  registry 登记
        │
        ├── keepalive tick (cron 每 6h)  ── 打开 muse.ai → 确认登录 → 重导 auth.json（滑动保活）
        │
        ├── 跨机无损迁移：拷 auth.json → 新机 accounts import（_resolve 按尾段重建 profile/auth 路径）
        │
        └── cred_extract verify <id>  ── 纯 auth.json 开一次性 context，不依赖 profile，验凭证真伪
```

**无损迁移关键点**：Muse 登录态由两部分组成——cookies(`hatch_sess`/`hatch_gw` 等) +
`origins[].localStorage`。`dump_state` 在 `storage_state()` 后用 `ctx.cookies()` 的
`expires` 回填（Playwright 对 session cookie 写 0/-1，导致 `days_left` 读空），
`cred_extract import`/`accounts.py import` 再把 cookies + localStorage 一并灌入新 profile，
`verify` 实测 `credential_valid:true` 即无损。

## 关键设计决策

1. **DOM 桥而不是 API**：Muse 没有公开 API；用用户自己的浏览器登录态是唯一
   不引入第三方凭证的路径。代价是选择器会漂移，因此有 `muse_status` 和
   自检/手工 login 作为观测面。
2. **唯一标记硬证送达**：发送文本带 `[ISHII-xxxxxx]` 标记，回读输入框确认
   后再按 Enter；失败重试换标记。不能把“已点击”当成“已送达”。
3. **账号隔离**：`accounts/<id>/profile` 是浏览器运行态，`auth.json` 是可移植
   的 storage_state；`registry.json` 记录代理和标签。按号分散，不共享 profile。
4. **零依赖协议层**：`mcp_server.py` 手写 stdio JSON-RPC，避免为了 MCP 引入
   一整套 SDK；执行层才依赖 Playwright。
5. **安装可自证**：安装器最后跑 `run_me.py --check`（语法 + initialize 握手），
   CI 再跑 `pytest` 和 installer dry-run；安装失败不会留一个“看起来装好了”的目录。
6. **默认失败可见**：MCP 错误返回 `error`，`worker`/`cli` 返回非零和 JSON 证据；
   不做静默重试掩盖登录墙/选择器漂移。
7. **凭证即 storage_state，expires 必填**：Playwright 的 `storage_state()` 对
   session cookie 写 `expires:0/-1`，迁移后 `days_left` 全空、无法判有效期。
   `dump_state` 用 `ctx.cookies()` 的真实 `expires` 回填，凭证才具备“剩余天数”
   语义，`list/verify/keepalive` 的保鲜判断才有依据。
8. **滑动保活代替重复登录**：Muse `hatch_sess` 服务端滑动续期（实测 10-14 登录
   → 10-21 仍有效，`keepalive` 跑一次 `days_left` 由 29.8 回升至 30.0）。定期
   打开页面即可续命，**不需要**存密码自动重登。
9. **自动填写评估结论（不做）**：登录页实际是「手机号/邮箱 → 短信/邮件验证码 +
   Meta OAuth」，DOM 里**没有** password 字段（input `autocomplete=username
   webauthn`，按钮仅「登录/继续」）。因此“填密码自动登录”在 Muse 上不成立；
   能自动填的只有手机号那一步，验证码无法也不应自动获取（风控绕过红线）。
   正确路径是 `cred_extract login` 人工登录一次 + `keepalive` 长期续期，
   把“重新面对登录墙”的概率降到最低，而非自动闯墙。
10. **跨机路径自愈 `_resolve`**：`registry.json` 里的 profile/auth 可能是上一台
    机器的绝对路径。`_resolve` 规则：相对→`MUSE_HOME` 展开；绝对但不存在→按尾段
    `accounts/...` 或 `chrome-full` 在 `MUSE_HOME` 下重建。拷贝目录即迁移，不依赖
    手改 registry。

## 内存与 24h 后台占用（实测）

- 保活是**无常驻**模型：`keepalive tick` 每 6h 由 cron 拉起一次，起一个 headless
  Chromium（新增进程峰值 **≈316MB**，含 profile 常驻 Chrome 基线时整机峰值≈1.2GB），
  跑完 `ctx.close()` 即全部释放——实测 tick 后新增 chrome 进程数 **0**。
- 24h 后台“开着”指的是 **cron 定时可达**，不是浏览器常驻吃内存；空闲时零进程占用。
- worker（send/poll）同理：一次调用起一次、结束即回收。

## 失败模式

| 现象 | 处理 |
|---|---|
| Muse 登录过期 | `muse_status` 报 `logged_in=false`；重新 `cred_extract login <id>` 或 `accounts import` |
| keepalive 报 `login_wall` / 进入 `dead` 列表 | 会话已死，需人工 `cred_extract login <id>` 重登（cron 错误审计会捕获） |
| composer 选择器漂移 | `muse_send` 返回 `COMPOSER_NOT_FOUND`；更新选择器/跑 `run_me --check` |
| `days_left:null` | auth.json 无 expires（旧导出）；跑 `cred_extract extract <id>` 或 `keepalive tick` 回填 |
| 代理不可用 | `setproxy` 后 `muse_status` 失败；换代理或 `setproxy <id> none` |
| 回复迟迟不出现 | `muse_poll` 超时返回，不伪造回复；检查 `muse_status`/页面截图 |
| 浏览器二进制缺失 | `install.py` 已装 Chromium；否则 `python -m playwright install chromium` |

## 安全边界

- `auth.json` 等价于账号凭证；`accounts/` 与 `chrome-full/` 已在 `.gitignore`。
- `cred_extract show` 默认对 cookie 值打码，`--secret` 才输出完整值（慎用）。
- `accounts export` **先验再写**：打开 muse.ai 检测不到 composer 时拒绝导出，
  绝不把登录墙空壳覆盖成可用凭证（实测防洗掉有效 auth）。
- 只读/写入范围限于 Muse 聊天页；不读取浏览器历史、书签、Cookie 以外的站点数据。
- 安装器不执行远程脚本；只调用本机 `pip` 和 `playwright`。

## 双机共用（local + server 共享同一 Muse 会话）

凭证是唯一真源，两台机器各持一份副本，互不干扰：

```
本地 (Windows)                          服务器 (Linux/107)
 accounts/muse-main/auth.json  ──scp──► /opt/muse-bridge/accounts/muse-main/auth.json
 cred_extract import → profile          accounts import → profile（一次性）
 keepalive (Hermes cron 每6h)            keepalive (crontab 每6h，日志 keepalive.log)
 worker send/poll                        worker send/poll
```

- **可行性依据**：Muse 登录态是 cookie(`hatch_sess`)+localStorage 的服务端会话，
  同凭证多端并发读取不互踢；每端 `keepalive tick` 都会滑动续期（重复刷新无害）。
- **服务器无需显示器**：`MUSE_CHROME` 指向 headless Chromium 即可（107 实测：
  `python3 -m muse_bridge.worker send/poll` 端到端 `delivered:true` + `reply:"收到"`）。
- **凭证轮换同步**：任一端 `cred_extract login` 重新登录产生新 auth.json 后，
  应重新 scp 同步到另一端（旧副本仍有效，直到服务端轮换为止）。
- **防封提示**：双端同时高频操作等于一个账号两路流量，建议错峰（本地白天、
  服务器夜间任务）或按计划做地区切割（见 Roadmap）。

## 测试与发布

```bash
python install.py --skip-browser   # 本地安装
python run_me.py --check           # 语法 + MCP 握手
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q   # 干净环境 3/3

# 凭证/保活（需真实账号，不进 CI）
python -m muse_bridge.cred_extract list                 # 凭证摘要
python -m muse_bridge.cred_extract verify muse-main     # 纯凭证验证 credential_valid
python -m muse_bridge.keepalive tick --account muse-main # 单号保活，看 days_left 回升
```

CI 在 Python 3.10/3.11/3.12 上跑同一套自动化命令；凭证/保活类需真实会话，
不纳入 CI，作为本机运维命令文档化。

## Roadmap 落地进度

- **账号隔离** ✅ 已实现：每号独立 `profile` / `auth` / `proxy`，`cred_extract`+`keepalive` 按号操作。
- **凭证提取与管理** ✅ 已实现：`cred_extract`（login/extract/list/verify/show），auth.json 即迁移单元。
- **跨机无损迁移** ✅ 已实现：`_resolve` 路径自愈 + cookies/localStorage 双注入 + `verify`。
- **账号自动保活** ✅ 已实现：`keepalive` + Hermes cron `a15b9fd60a9b` 每 6h，滑动续期实测有效。
- **地区切割防封号** ⏳ 部分：`setproxy` 已支持按号绑代理；按地区分配出口/指纹(locale/UA) 待做。
- **密码自动填写** ⛔ 不采纳：Muse 无密码字段（验证码/OAuth 流），自动闯墙属风控绕过红线（见决策 9）。

> 以上均为**未来计划，存在不确定性**，取决于作者实践；**若有人提前完成其中某项，
> 欢迎直接 PR / fork 强行合并**（同一目标先到先得），作者不会以“这是我的计划”为由拒绝。