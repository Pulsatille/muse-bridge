# 架构

## 数据流

```
MCP 客户端 / Hermes Agent
        │ stdio JSON-RPC
        ▼
muse_bridge.mcp_server.py   （协议层：initialize/tools-list/tools-call）
        │ subprocess（-X utf8，JSON 行扫描）
        ▼
muse_bridge.worker.py       （执行层：Playwright 持久上下文）
        │ Playwright CDP/浏览器协议
        ▼
本地 Chromium（headless）→ muse.ai 网页 composer
        │ DOM 注入 + Enter + 输入框校验 + 唯一标记硬证
        ▼
回复 → poll 轮询 DOM 稳定 → JSON 返回
```

## 数据结构

### accounts/registry.json

```json
{
  "default": "muse-default",
  "accounts": {
    "muse-default": {
      "profile": "accounts/muse-default/profile",
      "auth":    "accounts/muse-default/auth.json",
      "proxy":   null,
      "label":   "主号",
      "quota_note": "每周 10 亿 token"
    }
  }
}
```

### MCP 工具接口

| 工具 | 参数 | 返回关键字段 |
|------|------|--------------|
| muse_send | prompt, new_chat?, account? | ok / marker / delivered / account / proxy / url |
| muse_poll | timeout_s?, account? | ok / reply / account |
| muse_status | account? | ok / logged_in / login_wall / days_left / proxy |
| muse_accounts | — | accounts[]（id/label/proxy/days_left/default） |
| muse_export | account? | ok / auth（auth.json 路径） |

## 稳定性设计

- **唯一标记硬证送达**：发送内容带 `[ISHII-xxxxxx]` 标记，回读输入框校验后 Enter；失败自动重试一次并换新标记
- **新会话导航**：`--new-chat` 先开新会话再发，导航后 re-find 元素，避免 handle 失效
- **代理注入**：`setproxy` 后每个账号独立代理，分散额度/降低风控关联
- **认证保鲜**：`muse_export` 刷新 auth.json；`muse_status` 报告会话剩余天数

## 安全边界

- 绝不读取/上传浏览器历史、书签等无关数据，只操作 Muse 聊天页 DOM
- `auth.json` 是完整登录态（storage_state），等同于账号凭证 —— 请按密码保管，勿提交 git
