#!/usr/bin/env bash
# 107 最终验收：import 凭证→profile → worker status → send → poll（端到端）
set -e
cd /opt/muse-bridge
export PYTHONPATH=/opt/muse-bridge/src
export MUSE_HOME=/opt/muse-bridge
export MUSE_CHROME=/root/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
echo "[1/4] import auth.json -> profile"
python3 -X utf8 -m muse_bridge.accounts import muse-main
echo "[2/4] worker status"
python3 -X utf8 -m muse_bridge.worker status --account muse-main
echo "[3/4] worker send（端到端下发）"
python3 -X utf8 -m muse_bridge.worker send "只回复两个字：收到" --account muse-main --new-chat
echo "[4/4] worker poll（取回回复）"
python3 -X utf8 -m muse_bridge.worker poll --timeout 90 --account muse-main
echo ALL_DONE
