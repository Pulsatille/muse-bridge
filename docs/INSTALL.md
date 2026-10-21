# 安装与部署

## Windows 本机

```powershell
pip install -r requirements.txt
python -m playwright install chromium

# 首次登录（生成认证包）
python -m muse_bridge.cli login          # 或 accounts.py add muse-default --auth accounts/muse-default/auth.json
python -m muse_bridge.accounts list      # 应能看到账号
```

## Linux 服务器（headless）

```bash
apt-get install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2
pip install -r requirements.txt
python -m playwright install chromium

# 登录态在本机生成后，把 accounts/<id>/auth.json 拷到服务器同路径：
#   accounts/muse-default/auth.json
python -m muse_bridge.accounts import muse-default
python -m muse_bridge.worker status
```

## MCP 客户端接入（Hermes Agent 示例）

编辑 `~/.hermes/config.yaml`：

```yaml
mcp_servers:
  muse-bridge:
    command: python
    args: ["-X", "utf8", "-m", "muse_bridge.mcp_server"]
    cwd: "/path/to/muse-bridge/src"
```

然后 `hermes mcp test muse-bridge` 应显示 7 个工具。

## 代理（可选）

```bash
python -m muse_bridge.accounts setproxy muse-default socks5://user:pass@host:1080
```
