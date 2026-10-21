#!/usr/bin/env bash
# 107 安装 muse-bridge 保活 cron（每 6h tick，日志追加；幂等）
CHROME=/root/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
LINE="0 */6 * * * cd /opt/muse-bridge && PYTHONPATH=src MUSE_HOME=/opt/muse-bridge MUSE_CHROME=$CHROME /usr/bin/python3 -X utf8 -m muse_bridge.keepalive tick >> /opt/muse-bridge/keepalive.log 2>&1"
if crontab -l 2>/dev/null | grep -q muse_bridge.keepalive; then
  echo "cron already present, skip"
else
  (crontab -l 2>/dev/null; echo "$LINE") | crontab -
  echo "cron added"
fi
echo "--- crontab 确认 ---"
crontab -l 2>/dev/null | grep muse_bridge | head -1
