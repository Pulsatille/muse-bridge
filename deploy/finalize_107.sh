#!/usr/bin/env bash
# 107 侧部署收尾：拉新代码 → 凭证池重装验证 → 技能安装 → MCP 注册 → 双机登录态核验
set -x
cd /opt/muse-bridge || exit 1
git -c safe.directory='*' pull --ff-only -q origin main
git log --oneline -1

export PYTHONPATH=/opt/muse-bridge/src
export MUSE_HOME=/opt/muse-bridge
export MUSE_CHROME=/root/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome

echo "===== [A] 凭证池 unpack（--force --verify，双号） ====="
python3 -X utf8 -m muse_bridge.cred_bundle unpack /tmp/pool.tar.gz --force --verify | tail -32

echo "===== [B] pool status（107 池视图） ====="
python3 -X utf8 -m muse_bridge.pool status | head -30

echo "===== [C] 107 登录态核验（worker status 走 profile 实登 + 纯凭证 verify） ====="
python3 -X utf8 -m muse_bridge.accounts import muse-main | tail -1
python3 -X utf8 -m muse_bridge.worker status --account muse-main | tail -1

echo "===== [D] hermes 环境定位 ====="
ls /root/.local/bin/ 2>/dev/null | grep -iE 'hermes|muse' || echo "no-hermes-in-local-bin"
find /root /usr/local /opt -maxdepth 3 -name "hermes*" -type f 2>/dev/null | head -5
grep -n "mcp_servers" /root/.hermes/config.yaml | head -2

echo "===== [E] 技能安装到 107 Hermes ====="
mkdir -p /root/.hermes/skills/muse-bridge
cp -f /opt/muse-bridge/skills/muse-bridge/SKILL.md /root/.hermes/skills/muse-bridge/SKILL.md
ls -la /root/.hermes/skills/muse-bridge/

echo "===== [F] MCP 注册（写 config.yaml mcp_servers.muse-bridge，先备份） ====="
cp -f /root/.hermes/config.yaml /root/.hermes/config.yaml.bak-muse-bridge-$(date +%s)
python3 - <<'PY'
import io, re
p = "/root/.hermes/config.yaml"
t = io.open(p, encoding="utf-8").read()
block = (
    "  muse-bridge:\n"
    "    command: /usr/bin/python3\n"
    "    args:\n"
    "      - \"-X\"\n"
    "      - utf8\n"
    "      - \"-m\"\n"
    "      - muse_bridge.mcp_server\n"
    "    env:\n"
    "      PYTHONPATH: /opt/muse-bridge/src\n"
    "      MUSE_HOME: /opt/muse-bridge\n"
    "      MUSE_CHROME: /root/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome\n"
)
if "muse-bridge:" in t:
    print("muse-bridge already registered, skip")
elif "mcp_servers:" in t:
    t = t.replace("mcp_servers:\n", "mcp_servers:\n" + block, 1)
    io.open(p, "w", encoding="utf-8").write(t)
    print("muse-bridge added under mcp_servers")
else:
    io.open(p, "a", encoding="utf-8").write("\nmcp_servers:\n" + block)
    print("mcp_servers section created + muse-bridge added")
PY
grep -n "muse-bridge" -A 3 /root/.hermes/config.yaml | head -12
rm -f /tmp/pool.tar.gz
echo "ALL_DONE_107"
