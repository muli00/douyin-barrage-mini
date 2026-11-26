import os
import uvicorn

from engine import (
    LiveEngine,
    ensure_proto_compiled,
    normalize_live_url,
    resolve_cdp_ws_endpoint,
)
from server import create_app

__all__ = [
    "ensure_proto_compiled",
    "normalize_live_url",
    "resolve_cdp_ws_endpoint",
]


def main() -> None:
    ensure_proto_compiled()
    web_port = int(os.getenv("WEB_PORT", "8889"))
    ws_port = int(os.getenv("WS_PORT", "8888"))

    engine = LiveEngine(
        config_path="config.json",
        pitch_path="pitch.txt",
        knowledge_path="knowledge.txt",
        ws_port=ws_port,
    )
    app = create_app(engine)

    print("=" * 62)
    print(f"🎙️ AI 直播助播导播台已启动 -> 请用浏览器打开: http://127.0.0.1:{web_port}")
    print(f"📡 原始弹幕 WebSocket 转发端口 -> ws://127.0.0.1:{ws_port}")
    print("=" * 62)

    uvicorn.run(app, host="0.0.0.0", port=web_port, log_level="warning")


if __name__ == "__main__":
    main()
