"""本地测试客户端：连接 ws://127.0.0.1:8888 实时接收转发的 JSON 弹幕。"""

import asyncio
import json
import os

import websockets


async def listen() -> None:
    url = os.getenv("WS_URL", "ws://127.0.0.1:8888")
    print(f"[Client] 正在连接 {url} ...")
    async with websockets.connect(url) as ws:
        print("[Client] 连接成功，等待弹幕推送...")
        async for raw in ws:
            data = json.loads(raw)
            print(f"[收到广播] {json.dumps(data, ensure_ascii=False)}")


if __name__ == "__main__":
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        print("\n[Client] 已断开。")
