import asyncio
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv


def ensure_proto_compiled() -> None:
    """如果 douyin_pb2.py 不存在或 .proto 有更新，自动调用 protoc 编译。"""
    proto_file = Path("proto/douyin.proto")
    pb2_file = Path("douyin_pb2.py")
    if not pb2_file.exists() or proto_file.stat().st_mtime > pb2_file.stat().st_mtime:
        print("[Proto] 正在编译 proto/douyin.proto -> douyin_pb2.py ...")
        subprocess.run(
            ["protoc", "-I", "proto", "--python_out=.", "proto/douyin.proto"],
            check=True,
        )


def normalize_live_url(raw_url: str) -> str:
    """兼容带 live_web_rid 参数的抖音长链接，自动转换为标准短链接。"""
    parsed = urlparse(raw_url.strip())
    qs = parse_qs(parsed.query)
    rid = qs.get("live_web_rid", [None])[0]
    if rid:
        return f"https://live.douyin.com/{rid}"
    return raw_url.strip()


def format_console_log(msg: dict) -> str:
    msg_type = msg.get("type")
    if msg_type == "chat":
        return f"[弹幕] {msg['nickname']}: {msg['content']}"
    if msg_type == "gift":
        return f"[礼物] {msg['nickname']} 送出 {msg['gift_name']} x{msg['count']}"
    if msg_type == "like":
        return f"[点赞] {msg['nickname']} 点了 {msg['count']} 个赞 (总赞: {msg['total']})"
    if msg_type == "member":
        return f"[进房] {msg['nickname']} 进入了直播间"
    if msg_type == "follow":
        return f"[关注] {msg['nickname']} 关注了主播"
    if msg_type == "stats":
        return f"[在线] 当前在线: {msg['online_text']} ({msg['online_count']})"
    return str(msg)


async def run() -> None:
    # 自动加载本地 .env 文件（若存在，不覆盖命令行显式传入的环境变量）
    load_dotenv(override=False)
    ensure_proto_compiled()

    from playwright.async_api import async_playwright

    from ai_assistant import AIAssistant
    from decoder import decode_frame
    from sender import BarrageSender, inject_cookies_if_exists
    from ws_server import LocalWSServer

    raw_live_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("LIVE_URL", "https://live.douyin.com/")
    )
    live_url = normalize_live_url(raw_live_url)
    ws_host = os.getenv("WS_HOST", "0.0.0.0")
    ws_port = int(os.getenv("WS_PORT", "8888"))
    headless = os.getenv("HEADLESS", "true").lower() in ("1", "true", "yes")
    only_chat = os.getenv("ONLY_CHAT", "true").lower() in ("1", "true", "yes")

    mode_text = (
        "仅输出弹幕 (ONLY_CHAT=true)"
        if only_chat
        else "输出全部消息 (ONLY_CHAT=false)"
    )
    print(f"[Filter] 当前模式: {mode_text}")

    ai_assistant = AIAssistant(knowledge_path="knowledge.txt")
    ws_server = LocalWSServer(host=ws_host, port=ws_port)
    await ws_server.start()

    barrage_ws_ids: set[str] = set()

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir="./chrome_profile",
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        # 方法一：启动后自动注入项目根目录的 cookies.json（若存在）
        await inject_cookies_if_exists(context, cookie_path="cookies.json")

        page = context.pages[0] if context.pages else await context.new_page()
        sender = BarrageSender(page)

        async def handle_ai_reply(msg: dict) -> None:
            reply = await ai_assistant.generate_reply(
                msg["nickname"], msg["content"]
            )
            if not reply:
                return
            if ai_assistant.dry_run:
                print(
                    f"[AI 演习回复] 针对「{msg['nickname']}: {msg['content']}」-> {reply}"
                )
            else:
                await sender.send(reply)

        cdp = await context.new_cdp_session(page)
        await cdp.send("Network.enable")

        def on_ws_created(event: dict) -> None:
            url = event.get("url", "")
            if "webcast" in url and "push" in url:
                barrage_ws_ids.add(event["requestId"])
                print(f"[CDP] 已捕获弹幕 WSS 连接: {url[:80]}...")

        def on_ws_frame_received(event: dict) -> None:
            if event.get("requestId") not in barrage_ws_ids:
                return
            resp = event.get("response", {})
            if resp.get("opcode") != 2:
                return
            try:
                messages = decode_frame(resp["payloadData"])
                for msg in messages:
                    if only_chat and msg.get("type") != "chat":
                        continue
                    print(format_console_log(msg))
                    asyncio.create_task(ws_server.broadcast(msg))
                    if ai_assistant.enabled and msg.get("type") == "chat":
                        asyncio.create_task(handle_ai_reply(msg))
            except Exception as exc:
                print(f"[Decode Error] {exc}")

        cdp.on("Network.webSocketCreated", on_ws_created)
        cdp.on("Network.webSocketFrameReceived", on_ws_frame_received)

        print(f"[Browser] 正在打开直播间 (headless={headless}): {live_url}")
        await page.goto(live_url, wait_until="domcontentloaded", timeout=60000)
        print("[Browser] 页面已打开，正在监听弹幕流... 按 Ctrl+C 退出")

        try:
            await asyncio.Future()
        finally:
            await context.close()
            await ws_server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[Main] 已停止监听。")
