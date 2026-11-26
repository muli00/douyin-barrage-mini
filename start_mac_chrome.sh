#!/usr/bin/env bash
set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
PROFILE_DIR="$BASE_DIR/mac_chrome_profile"
mkdir -p "$PROFILE_DIR"

# 后台顺带启动 Mac 原生音频监听播放（退出时自动回收）
bash "$BASE_DIR/play_audio.sh" &
AUDIO_PID=$!
trap 'kill $AUDIO_PID 2>/dev/null || true' EXIT

echo "[Mac Chrome] 正在启动独立助播浏览器窗口（已同步开启 Mac 本地语音播放）..."
echo "[Mac Chrome] 调试端口: 127.0.0.1:9222"
echo "[Mac Chrome] 独立目录: $PROFILE_DIR（与你日常使用的 Chrome 完全隔离）"

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --remote-allow-origins=* \
  --user-data-dir="$PROFILE_DIR" \
  --no-first-run \
  --no-default-browser-check \
  "https://live.douyin.com/"
