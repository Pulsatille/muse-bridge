#!/usr/bin/env bash
# 107：以 cron 同款环境变量实跑一次 keepalive，验证日志链路
cd /opt/muse-bridge
export PYTHONPATH=src MUSE_HOME=/opt/muse-bridge
export MUSE_CHROME=/root/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
/usr/bin/python3 -X utf8 -m muse_bridge.keepalive tick >> /opt/muse-bridge/keepalive.log 2>&1
echo "rc=$?"
echo "--- keepalive.log 尾 ---"
tail -4 /opt/muse-bridge/keepalive.log
