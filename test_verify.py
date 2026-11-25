"""自测脚本：验证解包、本地 WS 广播、Playwright+CDP、Cookie 清洗与 AI 过滤全链路。"""

import asyncio
import base64
import gzip
import json
import os

import websockets

import douyin_pb2
from ai_assistant import AIAssistant
from decoder import decode_frame
from main import normalize_live_url, resolve_cdp_ws_endpoint
from sender import normalize_cookies
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
    print("[PASS] 1/5 Protobuf + gzip + Base64 解包自测通过")

    # 2. 验证本地 WS 广播链路
    server = LocalWSServer(host="127.0.0.1", port=18888)
    await server.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18888") as client:
            await asyncio.sleep(0.05)
            await server.broadcast(messages[0])
            received = json.loads(await asyncio.wait_for(client.recv(), timeout=2.0))
            assert received == messages[0], f"广播数据不匹配: {received}"
            print("[PASS] 2/5 本地 WebSocket 广播自测通过")
    finally:
        await server.stop()

    # 3. 验证 Playwright Chromium + CDP 启动
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Network.enable")
            print("[PASS] 3/5 Playwright Chromium + CDP 会话启动自测通过")
        finally:
            await browser.close()

    # 4. 验证 Cookie 规范化与长链接提取
    raw_cookies = [
        {
            "name": "sessionid",
            "value": "mock_val",
            "domain": ".douyin.com",
            "path": "/",
            "expirationDate": 1999999999.0,
            "sameSite": "no_restriction",
            "secure": False,
        }
    ]
    cleaned = normalize_cookies(raw_cookies)
    assert len(cleaned) == 1
    assert cleaned[0]["sameSite"] == "None" and cleaned[0]["secure"] is True
    assert cleaned[0]["expires"] == 1999999999.0
    assert (
        normalize_live_url("https://live.douyin.com/?anchor_id=1&live_web_rid=751561170106")
        == "https://live.douyin.com/751561170106"
    )
    print("[PASS] 4/5 Cookie 规范化与长链接提取自测通过")

    # 5. 验证 AI 助播规则过滤与违禁词拦截
    os.environ["AI_ENABLED"] = "true"
    os.environ["LLM_API_KEY"] = "sk-mock-key"
    os.environ["BOT_NICKNAME"] = "我的助播小号"
    os.environ["BANNED_WORDS"] = "全网第一,微信"
    bot = AIAssistant()
    assert bot.should_consider("我的助播小号", "多少钱") is False
    assert bot.should_consider("路人", "1") is False
    assert bot.should_consider("路人", "这件衣服怎么拍？") is True
    assert bot.contains_banned_word("这是全网第一好用的") == "全网第一"
    assert bot.contains_banned_word("点击小黄车1号链接就可以拍哦") is None
    ws_ep = resolve_cdp_ws_endpoint("ws://localhost:9222/devtools/browser/abc")
    assert ws_ep == "ws://localhost:9222/devtools/browser/abc"
    print("[PASS] 5/5 AI 助播过滤、违禁词拦截与 CDP 地址解析自测通过")


if __name__ == "__main__":
    asyncio.run(run_verify())
