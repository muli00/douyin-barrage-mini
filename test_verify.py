"""自测脚本：验证解包、WS 广播、Playwright+CDP、配置掩码、跨平台浏览器探测、TTS Base64 合成与 FastAPI 接口全链路。"""

import asyncio
import base64
import gzip
import json
import os
import tempfile
from pathlib import Path

import websockets
from fastapi.testclient import TestClient

import douyin_pb2
from ai_assistant import AIAssistant
from app_config import AppConfig
from decoder import decode_frame
from engine import LiveEngine, normalize_live_url, resolve_cdp_ws_endpoint
from launch_browser import find_chromium_binary
from sender import normalize_cookies
from server import create_app
from voice_speaker import synthesize_tts_b64
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
    assert len(messages) == 2 and messages[0]["content"] == "666 主播太强了"
    print("[PASS] 1/7 Protobuf + gzip + Base64 解包自测通过")

    # 2. 验证本地 WS 广播链路
    server = LocalWSServer(host="127.0.0.1", port=18888)
    await server.start()
    try:
        async with websockets.connect("ws://127.0.0.1:18888") as client:
            await asyncio.sleep(0.05)
            await server.broadcast(messages[0])
            received = json.loads(await asyncio.wait_for(client.recv(), timeout=2.0))
            assert received == messages[0]
            print("[PASS] 2/7 本地 WebSocket 广播自测通过")
    finally:
        await server.stop()

    # 3. 验证 Playwright Chromium + CDP 启动与跨平台浏览器探测
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Network.enable")
            _ = find_chromium_binary()
            print("[PASS] 3/7 Playwright Chromium + CDP 与跨平台浏览器探测自测通过")
        finally:
            await browser.close()

    # 4. 验证 Cookie 规范化与长链接提取
    cleaned = normalize_cookies(
        [
            {
                "name": "sessionid",
                "value": "mock_val",
                "domain": ".douyin.com",
                "expirationDate": 1999999999.0,
                "sameSite": "no_restriction",
            }
        ]
    )
    assert len(cleaned) == 1 and cleaned[0]["sameSite"] == "None" and cleaned[0]["secure"] is True
    assert (
        normalize_live_url("https://live.douyin.com/?anchor_id=1&live_web_rid=751561170106")
        == "https://live.douyin.com/751561170106"
    )
    assert (
        resolve_cdp_ws_endpoint("ws://localhost:9222/devtools/browser/abc")
        == "ws://localhost:9222/devtools/browser/abc"
    )
    print("[PASS] 4/7 Cookie 规范化、长链转换与 CDP 地址解析自测通过")

    # 5. 验证 AppConfig 密钥脱敏保护与 AI 热更新
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "config.json"
        os.environ["LLM_API_KEY"] = "sk-abcdef1234567890"
        cfg = AppConfig(config_path=str(cfg_file))
        pub = cfg.to_public_dict()
        assert "llm_api_key" not in pub and pub["llm_api_key_masked"] == "sk-****7890"
        # 传空字符串不应清空已有密钥
        cfg.update({"llm_api_key": "", "bot_nickname": "测试助播"})
        assert cfg.get("llm_api_key") == "sk-abcdef1234567890"
        bot = AIAssistant(config=cfg.data)
        assert bot.should_consider("测试助播", "怎么买") is False
        assert bot.should_consider("观众A", "1号链接怎么买") is True
    print("[PASS] 5/7 AppConfig 密钥脱敏保护与 AI 热更新过滤自测通过")

    # 6. 验证 edge-tts 内存流式 Base64 合成（跨平台前端直接播放格式）
    audio_b64 = await synthesize_tts_b64("欢迎来到直播间", voice="zh-CN-XiaoxiaoNeural")
    raw_mp3 = base64.b64decode(audio_b64)
    assert len(raw_mp3) > 1000
    print(f"[PASS] 6/7 edge-tts 内存流式 Base64 合成自测通过 (大小: {len(raw_mp3)} bytes)")


def run_fastapi_verify() -> None:
    # 7. 验证 FastAPI 中控台静态页、REST API 与 WebSocket 实时通道
    with tempfile.TemporaryDirectory() as tmpdir:
        eng = LiveEngine(
            config_path=str(Path(tmpdir) / "config.json"),
            pitch_path="pitch.txt",
            knowledge_path="knowledge.txt",
            ws_port=18889,
        )
        app = create_app(eng)
        with TestClient(app) as client:
            r_idx = client.get("/")
            assert r_idx.status_code == 200 and "AI 直播助播导播台" in r_idx.text

            r_state = client.get("/api/state")
            assert r_state.status_code == 200
            st = r_state.json()
            assert st["type"] == "state" and "llm_api_key" not in st["config"]

            r_cfg = client.post("/api/config", json={"dry_run": True, "reply_cooldown": 15})
            assert r_cfg.status_code == 200 and r_cfg.json()["config"]["reply_cooldown"] == 15

            with client.websocket_connect("/ws") as ws:
                first_msg = json.loads(ws.receive_text())
                assert first_msg["type"] == "state"
                ws.send_text(json.dumps({"event": "audio_ended"}))
    print("[PASS] 7/7 FastAPI 导播台页面、REST 接口与 WebSocket 双向通道自测通过")


if __name__ == "__main__":
    asyncio.run(run_verify())
    run_fastapi_verify()
