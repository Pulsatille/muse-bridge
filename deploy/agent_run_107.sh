#!/usr/bin/env bash
# 107：智能体实操验证——池选路 send → poll 取回复（等价于 Hermes 调 muse_send/muse_poll）
cd /opt/muse-bridge || exit 1
export PYTHONPATH=/opt/muse-bridge/src
export MUSE_HOME=/opt/muse-bridge
export MUSE_CHROME=/root/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome

echo "===== [1] pool next（107 智能体的自动选号） ====="
python3 -X utf8 -m muse_bridge.pool next | tail -n 2

echo "===== [2] send via pool（只回复：收到107） ====="
timeout 300 python3 -X utf8 -m muse_bridge.worker send "只回复六个字：收到107号机" --account pool --new-chat > /tmp/send107.json 2>&1
tail -n 1 /tmp/send107.json

echo "===== [3] poll via pool（取回回复） ====="
timeout 200 python3 -X utf8 -m muse_bridge.worker poll --timeout 120 --account pool > /tmp/poll107.json 2>&1
tail -n 1 /tmp/poll107.json

echo "===== [4] 池使用回报后的状态（today_uses 应 +1） ====="
python3 -X utf8 -m muse_bridge.pool status | grep -E '"id"|"days_left"|"today_uses"|"usable"' | head -n 8
rm -f /tmp/send107.json /tmp/poll107.json
echo "AGENT_RUN_DONE"
