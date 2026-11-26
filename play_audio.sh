#!/usr/bin/env bash
set -e

AUDIO_DIR="$(cd "$(dirname "$0")" && pwd)/audio_out"
AUDIO_FILE="$AUDIO_DIR/current.mp3"
mkdir -p "$AUDIO_DIR"
rm -f "$AUDIO_FILE"

echo "[Mac Audio] 🔊 本地语音播放器已启动，正在监听 $AUDIO_FILE ..."
echo "[Mac Audio] 提示：可将 Mac 通过直播内录线连接手机，或直接扬声器外放收音（按 Ctrl+C 停止）。"

while true; do
  if [ -f "$AUDIO_FILE" ]; then
    afplay "$AUDIO_FILE" || true
    rm -f "$AUDIO_FILE"
  else
    sleep 0.2
  fi
done
