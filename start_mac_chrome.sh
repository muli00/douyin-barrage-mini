#!/usr/bin/env bash
set -e

PROFILE_DIR="$(cd "$(dirname "$0")" && pwd)/mac_chrome_profile"
mkdir -p "$PROFILE_DIR"

echo "[Mac Chrome] 正在启动独立助播浏览器窗口..."
echo "[Mac Chrome] 调试端口: 127.0.0.1:9222"
echo "[Mac Chrome] 独立目录: $PROFILE_DIR（与你日常使用的 Chrome 完全隔离）"
echo "[Mac Chrome] 首次打开请在弹出的窗口中手动扫码登录助播小号，登录一次后长期有效。"

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --remote-allow-origins=* \
  --user-data-dir="$PROFILE_DIR" \
  --no-first-run \
  --no-default-browser-check \
  "https://live.douyin.com/"
