import asyncio
import json
from typing import Set

import websockets
from websockets.asyncio.server import Server, ServerConnection


class LocalWSServer:
    """本地 WebSocket 广播服务，将清洗后的弹幕实时推送给所有下游客户端。"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8888):
        self.host = host
        self.port = port
        self.clients: Set[ServerConnection] = set()
        self.server: Server | None = None

    async def _handler(self, ws: ServerConnection) -> None:
        self.clients.add(ws)
        print(f"[WS] 下游客户端已连接，当前在线: {len(self.clients)}")
        try:
            async for _ in ws:
                pass
        finally:
            self.clients.discard(ws)
            print(f"[WS] 下游客户端已断开，当前在线: {len(self.clients)}")

    async def start(self) -> None:
        self.server = await websockets.serve(self._handler, self.host, self.port)
        print(f"[WS] 本地广播服务已启动: ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def broadcast(self, message: dict) -> None:
        if not self.clients:
            return
        text = json.dumps(message, ensure_ascii=False)
        await asyncio.gather(
            *(client.send(text) for client in list(self.clients)),
            return_exceptions=True,
        )
