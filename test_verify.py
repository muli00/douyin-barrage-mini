"""自测脚本：构造模拟的抖音 Protobuf + gzip + Base64 帧，验证解包与本地 WS 广播全链路。"""

import asyncio
import base64
import gzip
import json

import websockets

import douyin_pb2
from decoder import decode_frame
from ws_server import LocalWSServer


def build_mock_b64_frame() -> str:
    chat = douyin_pb2.ChatMessage(
        user=douyin_pb2.User(id=10086, nickName="测试观众"),
        content="666 主播太强了",
    )
    gift = douyin_pb2.GiftMessage(
        giftId=1,
        comboCount=5,
        user=douyin_pb2.User(id=10087, nickName="榜一大哥"),
        gift=douyin_pb2.GiftStruct(name="小心心", diamondCount=1),
    )

    resp = douyin_pb2.Response(
        messagesList=[
            douyin_pb2.Message(
                method="WebcastChatMessage",
                payload=chat.SerializeToString(),
                msgId=1,
            ),
            douyin_pb2.Message(
                method="WebcastGiftMessage",
                payload=gift.SerializeToString(),
                msgId=2,
            ),
        ]
    )
    compressed = gzip.compress(resp.SerializeToString())
    frame = douyin_pb2.PushFrame(payload=compressed)
    return base64.b64encode(frame.SerializeToString()).decode("ascii")


async def run_verify() -> None:
    # 1. 验证解包链路
    mock_b64 = build_mock_b64_frame()
    messages = decode_frame(mock_b64)
    assert len(messages) == 2, f"期望 2 条消息，实际 {len(messages)}"
    assert messages[0]["type"] == "chat" and messages[0]["content"] == "666 主播太强了"
    assert messages[1]["type"] == "gift" and messages[1]["gift_name"] == "小心心"
    print("[PASS] 1/2 Protobuf + gzip + Base64 解包自测通过:", messages)

    # 2. 验证本地 WS 广播链路
    server = LocalWSServer(host="127.0.0.1", port=18888)
    await server.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18888") as client:
            await asyncio.sleep(0.05)
            await server.broadcast(messages[0])
            received = json.loads(await asyncio.wait_for(client.recv(), timeout=2.0))
            assert received == messages[0], f"广播数据不匹配: {received}"
            print("[PASS] 2/2 本地 WebSocket 广播自测通过:", received)
    finally:
        await server.stop()

    # 3. 验证 Playwright Chromium + CDP 在容器内正常启动
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Network.enable")
            print("[PASS] 3/3 Playwright Chromium + CDP 会话启动自测通过")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run_verify())
