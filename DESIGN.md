# Design

muse-bridge 把本地 AI 智能体接到**用户自己的 Muse 网页会话**上。它不做官方 API
逆向，也不托管账号；桥的是浏览器里的真实登录态和 DOM。

## 目标

- 任何 MCP 客户端（Hermes、Claude Code、Codex、Cursor 等）都能用
  `muse_send / muse_poll / muse_status / muse_accounts / muse_export` 五个工具。
- 一次安装、可迁移、可自检：`install.py` 建 venv、装依赖/Chromium、跑
  `run_me.py --check`。
- 多账号隔离：每号独立 profile、独立代理、独立可移植 `auth.json`。

## 非目标

- 不绕过 Muse 的额度、风控或登录限制；不批量注册账号。
- 不读取浏览器历史/书签/无关页面；只操作 Muse 聊天页 DOM。
- 不做多租户/公网服务；这是本机单用户桥。
- 不把 `auth.json` 或 `accounts/` 放进 git。

## 组件

| 文件 | 职责 |
|---|---|
| `src/muse_bridge/mcp_server.py` | stdio JSON-RPC 协议层；`initialize`/`tools/list`/`tools/call`；零第三方依赖 |
| `src/muse_bridge/worker.py` | 执行层；Playwright 持久上下文、DOM 注入、投递校验、回复轮询 |
| `src/muse_bridge/accounts.py` | 账号注册表 + profile/auth/proxy 三件套 + 导入导出 |
| `src/muse_bridge/cli.py` | 首次登录与生产冒烟脚本 |
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
```

详细的数据结构与工具返回字段见 `docs/ARCHITECTURE.md`。

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

## 失败模式

| 现象 | 处理 |
|---|---|
| Muse 登录过期 | `muse_status` 报 `logged_in=false`；重新 `cli login` 或 `accounts import` |
| composer 选择器漂移 | `muse_send` 返回 `COMPOSER_NOT_FOUND`；更新选择器/跑 `run_me --check` |
| 代理不可用 | `setproxy` 后 `muse_status` 失败；换代理或 `setproxy <id> none` |
| 回复迟迟不出现 | `muse_poll` 超时返回，不伪造回复；检查 `muse_status`/页面截图 |
| 浏览器二进制缺失 | `install.py` 已装 Chromium；否则 `python -m playwright install chromium` |

## 安全边界

- `auth.json` 等价于账号凭证；`accounts/` 与 `chrome-full/` 已在 `.gitignore`。
- 只读/写入范围限于 Muse 聊天页；不读取浏览器历史、书签、Cookie 以外的站点数据。
- 安装器不执行远程脚本；只调用本机 `pip` 和 `playwright`。

## 测试与发布

```bash
python install.py --skip-browser   # 本地安装
python run_me.py --check           # 语法 + MCP 握手
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q   # 干净环境 3/3
```

CI 在 Python 3.10/3.11/3.12 上跑同一套命令；安装器 dry-run 只打印命令，不写盘。
