import asyncio
import os
import subprocess
import sys
from pathlib import Path


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
    ensure_proto_compiled()

    from playwright.async_api import async_playwright
    from decoder import decode_frame
    from ws_server import LocalWSServer

    live_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("LIVE_URL", "https://live.douyin.com/")
    )
    ws_host = os.getenv("WS_HOST", "0.0.0.0")
    ws_port = int(os.getenv("WS_PORT", "8888"))
    headless = os.getenv("HEADLESS", "true").lower() in ("1", "true", "yes")
    only_chat = os.getenv("ONLY_CHAT", "true").lower() in ("1", "true", "yes")

    mode_text = "仅输出弹幕 (ONLY_CHAT=true)" if only_chat else "输出全部消息 (ONLY_CHAT=false)"
    print(f"[Filter] 当前模式: {mode_text}")

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
        page = context.pages[0] if context.pages else await context.new_page()

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
