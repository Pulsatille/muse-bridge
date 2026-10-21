#!/usr/bin/env bash
# 107：验证 muse-bridge MCP 被 Hermes 识别 + 技能加载
export PATH=/root/.local/bin:$PATH
cd /opt/muse-bridge || exit 1

echo "===== [1] hermes mcp test muse-bridge ====="
timeout 150 hermes mcp test muse-bridge > /tmp/mcptest.log 2>&1
echo "rc=$?"
tail -n 20 /tmp/mcptest.log

echo ""
echo "===== [2] 关键断言：连接 + 工具数 ====="
grep -iE "connect|muse_send|muse_poll|muse_pool|muse_cred|tool" /tmp/mcptest.log | head -n 12
echo "工具出现数: $(grep -oE 'muse_(send|poll|status|accounts|export|pool|cred)' /tmp/mcptest.log | sort -u | wc -l)/7"

echo ""
echo "===== [3] 技能是否被 Hermes 发现 ====="
timeout 60 hermes skills list 2>/dev/null | grep -iE "muse" || ls /root/.hermes/skills/muse-bridge/
rm -f /tmp/mcptest.log
echo "PROBE_DONE"
