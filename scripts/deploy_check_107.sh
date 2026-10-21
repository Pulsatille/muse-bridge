#!/usr/bin/env bash
# 107 muse-bridge 部署验证（stdin 执行，避免引号转义）
set -e
cd /opt/muse-bridge
export PYTHONPATH=/opt/muse-bridge/src
export MUSE_HOME=/opt/muse-bridge
PY=python3

echo "--- deps ---"
$PY -c 'import playwright, yaml; print("deps OK")'
$PY -m playwright --version

echo "--- 语法编译 ---"
$PY -m py_compile src/muse_bridge/mcp_server.py src/muse_bridge/worker.py \
    src/muse_bridge/accounts.py src/muse_bridge/cli.py \
    src/muse_bridge/cred_extract.py src/muse_bridge/keepalive.py
echo "py_compile OK"

echo "--- MCP initialize 握手 ---"
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n' \
  | $PY -X utf8 -m muse_bridge.mcp_server | head -c 200
echo

echo "--- 凭证摘要 ---"
$PY -X utf8 -m muse_bridge.cred_extract list

echo "--- 纯凭证验证（无损迁移证明） ---"
$PY -X utf8 -m muse_bridge.cred_extract verify muse-main --timeout 90
