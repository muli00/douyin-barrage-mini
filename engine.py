import asyncio
import collections
import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set
from urllib.parse import parse_qs, urlparse

from ai_assistant import AIAssistant
from app_config import AppConfig
from decoder import decode_frame
from sender import BarrageSender, inject_cookies_if_exists
from voice_speaker import VOICE_PRESETS, parse_pitch_text, synthesize_tts_b64
from ws_server import LocalWSServer


def ensure_proto_compiled() -> None:
    proto_file = Path("proto/douyin.proto")
    pb2_file = Path("douyin_pb2.py")
    if not pb2_file.exists() or proto_file.stat().st_mtime > pb2_file.stat().st_mtime:
        print("[Proto] 正在编译 proto/douyin.proto -> douyin_pb2.py ...")
        subprocess.run(
            ["protoc", "-I", "proto", "--python_out=.", "proto/douyin.proto"],
            check=True,
        )


def normalize_live_url(raw_url: str) -> str:
    parsed = urlparse((raw_url or "").strip())
    qs = parse_qs(parsed.query)
    rid = qs.get("live_web_rid", [None])[0]
    if rid:
        return f"https://live.douyin.com/{rid}"
    return (raw_url or "").strip()


def resolve_cdp_ws_endpoint(cdp_http_url: str) -> str:
    """将域名解析为 IP 地址并获取 WebSocket 调试地址，满足 Chrome/Edge 仅允许 IP / localhost 的校验。"""
    parsed = urlparse(cdp_http_url.strip())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 9222
    host_ip = host if host == "localhost" else socket.gethostbyname(host)

    if parsed.scheme in ("ws", "wss"):
        return parsed._replace(netloc=f"{host_ip}:{port}").geturl()

    version_url = f"http://{host_ip}:{port}/json/version"
    req = urllib.request.Request(version_url, headers={"Host": f"127.0.0.1:{port}"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        info = json.loads(resp.read().decode("utf-8"))

    ws_url = info["webSocketDebuggerUrl"]
    ws_parsed = urlparse(ws_url)
    return ws_parsed._replace(netloc=f"{host_ip}:{port}").geturl()


def format_interaction_event(msg: Dict[str, Any]) -> tuple[str, str, str]:
    """将解析后的互动字典转换为前端监控流友好的 (kind, title, detail)。"""
    mtype = msg.get("type", "system")
    nick = str(msg.get("nickname") or "匿名用户")
    if mtype == "chat":
        return ("chat", nick, str(msg.get("content") or ""))
    if mtype == "gift":
        gname = msg.get("gift_name") or "礼物"
        cnt = msg.get("count") or 1
        return ("gift", nick, f"送出 {gname} x{cnt}")
    if mtype == "like":
        cnt = msg.get("count") or 1
        total = msg.get("total") or 0
        return ("like", nick, f"点了 {cnt} 个赞（本场总赞 {total}）")
    if mtype == "follow":
        return ("follow", nick, "关注了主播")
    if mtype == "member":
        return ("member", nick, "进入了直播间")
    if mtype == "stats":
        online = msg.get("online_text") or msg.get("online_count") or 0
        return ("stats", "直播间热度", f"当前在线观众 {online}")
    return ("system", mtype, json.dumps(msg, ensure_ascii=False))


class LiveEngine:
    """核心业务编排引擎：动态连接/切换直播间、弹幕解码、双通道 AI 答疑、商品提取生稿与前端跨平台语音推送。"""

    def __init__(
        self,
        config_path: str = "config.json",
        pitch_path: str = "pitch.txt",
        knowledge_path: str = "knowledge.txt",
        ws_port: int = 8888,
    ) -> None:
        self.cfg = AppConfig(config_path=config_path)
        self.pitch_path = Path(pitch_path)
        self.ai = AIAssistant(knowledge_path=knowledge_path, config=self.cfg.data)
        self.barrage_ws = LocalWSServer(host="0.0.0.0", port=ws_port)

        # 房间连接状态
        self.room_status: str = "idle"  # idle | connecting | connected | error
        self.room_error: str = ""
        self.active_url: str = ""
        self._room_task: Optional[asyncio.Task] = None
        self._active_sender: Optional[BarrageSender] = None

        # 语音双轨队列与播报状态
        self.pitch_index: int = 0
        self.active_pitch_index: int = -1
        self.qa_queue: asyncio.Queue[Dict[str, str]] = asyncio.Queue(maxsize=40)
        self._voice_task: Optional[asyncio.Task] = None
        self._audio_ack = asyncio.Event()

        # 前端中控台 WebSocket 客户端集合与最近事件缓存
        self.ui_clients: Set[Any] = set()
        self.recent_events: Deque[Dict[str, Any]] = collections.deque(maxlen=80)

    def load_pitch_raw(self) -> str:
        if self.pitch_path.exists():
            return self.pitch_path.read_text(encoding="utf-8")
        return ""

    def load_pitch_lines(self) -> List[str]:
        return parse_pitch_text(self.load_pitch_raw())

    def save_pitch_raw(self, raw_text: str) -> List[str]:
        self.pitch_path.write_text(raw_text.strip() + "\n", encoding="utf-8")
        lines = self.load_pitch_lines()
        if self.pitch_index >= len(lines):
            self.pitch_index = 0
        return lines

    def build_state(self) -> Dict[str, Any]:
        lines = self.load_pitch_lines()
        return {
            "type": "state",
            "room_status": self.room_status,
            "room_error": self.room_error,
            "active_url": self.active_url,
            "config": self.cfg.to_public_dict(),
            "voices": VOICE_PRESETS,
            "pitch_raw": self.load_pitch_raw(),
            "pitch_lines": lines,
            "pitch_index": self.pitch_index,
            "active_pitch_index": self.active_pitch_index,
            "qa_queue_size": self.qa_queue.qsize(),
            "knowledge": self.ai.load_knowledge(),
            "ui_clients": len(self.ui_clients),
        }

    async def broadcast_ui(self, payload: Dict[str, Any]) -> None:
        if not self.ui_clients:
            return
        text = json.dumps(payload, ensure_ascii=False)
        dead = []
        for ws in list(self.ui_clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.ui_clients.discard(ws)

    async def push_event(self, kind: str, title: str, detail: str = "") -> None:
        ev = {
            "type": "event",
            "kind": kind,  # chat | text_reply | voice_qa | pitch | system | error
            "title": title,
            "detail": detail,
            "ts": time.strftime("%H:%M:%S"),
        }
        self.recent_events.append(ev)
        await self.broadcast_ui(ev)

    async def start(self) -> None:
        await self.barrage_ws.start()
        self._voice_task = asyncio.create_task(self._voice_loop())

    async def stop(self) -> None:
        await self.disconnect_room()
        if self._voice_task:
            self._voice_task.cancel()
            try:
                await self._voice_task
            except asyncio.CancelledError:
                pass
        await self.barrage_ws.stop()

    def update_config(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        self.cfg.update(patch)
        self.ai.apply_config(self.cfg.data)
        return self.cfg.to_public_dict()

    async def enqueue_voice_qa(
        self, nickname: str, question: str, reply_text: str
    ) -> None:
        if self.qa_queue.full():
            try:
                self.qa_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self.qa_queue.put(
            {"nickname": nickname, "question": question, "text": reply_text}
        )
        await self.broadcast_ui(self.build_state())

    async def send_manual_text(self, text: str) -> bool:
        if not self._active_sender or self.room_status != "connected":
            raise RuntimeError("当前尚未连接直播间，无法发送公屏弹幕。")
        ok = await self._active_sender.send(text)
        if ok:
            await self.push_event("text_reply", "导播手动公屏发言", text)
        return ok

    def jump_to_pitch(self, index: int) -> None:
        lines = self.load_pitch_lines()
        if lines:
            self.pitch_index = max(0, min(index, len(lines) - 1))
            self.update_config({"voice_enabled": True, "voice_pitch_enabled": True})

    async def connect_room(self, raw_url: Optional[str] = None) -> None:
        await self.disconnect_room()
        if raw_url:
            self.update_config({"live_url": normalize_live_url(raw_url)})
        target_url = normalize_live_url(self.cfg.get("live_url", ""))
        if not target_url or target_url.rstrip("/") == "https://live.douyin.com":
            raise ValueError("请先填写具体的抖音直播间地址（如 https://live.douyin.com/房间号）")

        self.room_status = "connecting"
        self.room_error = ""
        self.active_url = target_url
        await self.broadcast_ui(self.build_state())
        self._room_task = asyncio.create_task(self._run_room_session(target_url))

    async def disconnect_room(self) -> None:
        self._active_sender = None
        if self._room_task and not self._room_task.done():
            self._room_task.cancel()
            try:
                await self._room_task
            except asyncio.CancelledError:
                pass
        self._room_task = None
        self.room_status = "idle"
        self.active_url = ""
        await self.broadcast_ui(self.build_state())

    async def _run_room_session(self, live_url: str) -> None:
        from playwright.async_api import async_playwright

        cdp_url = str(self.cfg.get("cdp_url", "") or "").strip()
        headless = bool(self.cfg.get("headless", True))
        barrage_ws_ids: set[str] = set()

        try:
            async with async_playwright() as p:
                remote_browser = None
                if cdp_url:
                    ws_ep = resolve_cdp_ws_endpoint(cdp_url)
                    remote_browser = await p.chromium.connect_over_cdp(ws_ep)
                    context = (
                        remote_browser.contexts[0]
                        if remote_browser.contexts
                        else await remote_browser.new_context()
                    )
                    page = await context.new_page()
                else:
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir="./chrome_profile",
                        headless=headless,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                        ],
                    )
                    await inject_cookies_if_exists(context, cookie_path="cookies.json")
                    page = context.pages[0] if context.pages else await context.new_page()

                sender = BarrageSender(page)
                self._active_sender = sender

                async def handle_ai_reply(msg: dict) -> None:
                    need_text = bool(self.cfg.get("text_reply_enabled", True))
                    need_voice = bool(
                        self.cfg.get("voice_enabled", True)
                        and self.cfg.get("voice_qa_enabled", True)
                    )
                    dual = await self.ai.generate_dual_reply(
                        msg["nickname"],
                        msg["content"],
                        need_text=need_text,
                        need_voice=need_voice,
                    )
                    if not dual:
                        return

                    if need_voice and dual.get("voice_reply"):
                        await self.enqueue_voice_qa(
                            msg["nickname"], msg["content"], dual["voice_reply"]
                        )
                        await self.push_event(
                            "voice_qa",
                            f"语音答疑入队 @{msg['nickname']}",
                            dual["voice_reply"],
                        )

                    if need_text and dual.get("text_reply"):
                        if self.ai.dry_run:
                            await self.push_event(
                                "text_reply",
                                f"[演习不真发] 回复 @{msg['nickname']}",
                                dual["text_reply"],
                            )
                        else:
                            ok = await sender.send(dual["text_reply"])
                            tag = "公屏已回复" if ok else "公屏发送失败(请确认已登录)"
                            await self.push_event(
                                "text_reply" if ok else "error",
                                f"{tag} @{msg['nickname']}",
                                dual["text_reply"],
                            )

                cdp = await context.new_cdp_session(page)
                await cdp.send("Network.enable")

                def on_ws_created(event: dict) -> None:
                    url = event.get("url", "")
                    if "webcast" in url and "push" in url:
                        barrage_ws_ids.add(event["requestId"])
                        asyncio.create_task(
                            self.push_event("system", "已捕获抖音弹幕 WSS 数据流", live_url)
                        )

                def on_ws_frame_received(event: dict) -> None:
                    if event.get("requestId") not in barrage_ws_ids:
                        return
                    resp = event.get("response", {})
                    if resp.get("opcode") != 2:
                        return
                    try:
                        only_chat = bool(self.cfg.get("only_chat", True))
                        messages = decode_frame(resp["payloadData"])
                        for msg in messages:
                            if only_chat and msg.get("type") != "chat":
                                continue
                            asyncio.create_task(self.barrage_ws.broadcast(msg))
                            ev_kind, ev_title, ev_detail = format_interaction_event(msg)
                            asyncio.create_task(
                                self.push_event(ev_kind, ev_title, ev_detail)
                            )
                            if m_is_chat := (msg.get("type") == "chat"):
                                if self.ai.enabled and m_is_chat:
                                    asyncio.create_task(handle_ai_reply(msg))
                    except Exception as exc:
                        print(f"[Decode Error] {exc}")

                cdp.on("Network.webSocketCreated", on_ws_created)
                cdp.on("Network.webSocketFrameReceived", on_ws_frame_received)

                await page.goto(live_url, wait_until="domcontentloaded", timeout=60000)
                self.room_status = "connected"
                await self.broadcast_ui(self.build_state())
                await self.push_event("system", "直播间页面已打开，正在监听弹幕", live_url)

                disconnect_ev = asyncio.Event()
                page.on("close", lambda *_: disconnect_ev.set())
                if remote_browser is not None:
                    remote_browser.on("disconnected", lambda *_: disconnect_ev.set())

                try:
                    await disconnect_ev.wait()
                    self.room_status = "idle"
                    await self.push_event("system", "直播间标签页或浏览器已关闭", "")
                finally:
                    self._active_sender = None
                    if remote_browser is not None:
                        try:
                            if not page.is_closed():
                                await page.close()
                        except Exception:
                            pass
                    else:
                        await context.close()
                    await self.broadcast_ui(self.build_state())

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.room_status = "error"
            err_msg = str(exc)
            if cdp_url and ("9222" in err_msg or "urlopen" in err_msg or "Connect" in err_msg):
                err_msg = f"无法连接本机浏览器 ({cdp_url})，请先在宿主机运行 python3 launch_browser.py 打开浏览器窗口！"
            self.room_error = err_msg
            await self.push_event("error", "连接直播间失败", err_msg)
            await self.broadcast_ui(self.build_state())

    async def extract_and_generate_script(
        self, product_url: str, extra_notes: str
    ) -> Dict[str, Any]:
        """提取商品链接文本并调用大模型生成口播短句与知识库摘要。"""
        from playwright.async_api import async_playwright

        raw_text = ""
        url = (product_url or "").strip()
        if url and url.startswith(("http://", "https://")):
            cdp_url = str(self.cfg.get("cdp_url", "") or "").strip()
            async with async_playwright() as p:
                if cdp_url:
                    ws_ep = resolve_cdp_ws_endpoint(cdp_url)
                    browser = await p.chromium.connect_over_cdp(ws_ep)
                    ctx = (
                        browser.contexts[0]
                        if browser.contexts
                        else await browser.new_context()
                    )
                    temp_page = await ctx.new_page()
                    try:
                        await temp_page.goto(
                            url, wait_until="domcontentloaded", timeout=45000
                        )
                        await asyncio.sleep(3.0)
                        title = await temp_page.title()
                        body = await temp_page.evaluate(
                            "() => document.body ? document.body.innerText : ''"
                        )
                    finally:
                        await temp_page.close()
                else:
                    browser = await p.chromium.launch(
                        headless=True, args=["--no-sandbox"]
                    )
                    try:
                        temp_page = await browser.new_page()
                        await temp_page.goto(
                            url, wait_until="domcontentloaded", timeout=45000
                        )
                        await asyncio.sleep(3.0)
                        title = await temp_page.title()
                        body = await temp_page.evaluate(
                            "() => document.body ? document.body.innerText : ''"
                        )
                    finally:
                        await browser.close()

            compact = "\n".join(
                line.strip() for line in body.splitlines() if line.strip()
            )
            raw_text = f"页面标题：{title}\n页面可见文本摘录：\n{compact[:2500]}"

        return await self.ai.generate_product_script(raw_text, extra_notes)

    async def _voice_loop(self) -> None:
        """前端跨平台统一发声双轨主循环：优先插播答疑，空闲按句循环讲品。"""
        while True:
            try:
                if not self.ui_clients or not bool(self.cfg.get("voice_enabled", True)):
                    self.active_pitch_index = -1
                    await asyncio.sleep(0.4)
                    continue

                kind = None
                speak_text = ""
                meta: Dict[str, Any] = {}

                # 1. 高优先级：弹幕或手动语音插播
                if bool(self.cfg.get("voice_qa_enabled", True)) and not self.qa_queue.empty():
                    qa = await self.qa_queue.get()
                    kind = "qa"
                    speak_text = qa["text"]
                    meta = {
                        "nickname": qa["nickname"],
                        "question": qa["question"],
                    }
                # 2. 低优先级：日常循环讲品短句
                elif bool(self.cfg.get("voice_pitch_enabled", False)):
                    lines = self.load_pitch_lines()
                    if lines:
                        if self.pitch_index >= len(lines):
                            self.pitch_index = 0
                        cur_idx = self.pitch_index
                        self.active_pitch_index = cur_idx
                        kind = "pitch"
                        speak_text = lines[cur_idx]
                        meta = {
                            "index": cur_idx,
                            "line_no": cur_idx + 1,
                            "total_lines": len(lines),
                        }
                        self.pitch_index = (cur_idx + 1) % len(lines)

                if not speak_text:
                    self.active_pitch_index = -1
                    await asyncio.sleep(0.35)
                    continue

                voice = str(self.cfg.get("tts_voice", "zh-CN-XiaoxiaoNeural"))
                rate = str(self.cfg.get("tts_rate", "+8%"))
                audio_b64 = await synthesize_tts_b64(
                    speak_text, voice=voice, rate=rate
                )

                self._audio_ack.clear()
                await self.broadcast_ui(
                    {
                        "type": "speak",
                        "kind": kind,
                        "text": speak_text,
                        "meta": meta,
                        "audio_b64": audio_b64,
                        "active_pitch_index": self.active_pitch_index,
                        "pitch_index": self.pitch_index,
                        "qa_queue_size": self.qa_queue.qsize(),
                    }
                )

                timeout = max(8.0, len(speak_text) * 0.45 + 3.0)
                try:
                    await asyncio.wait_for(self._audio_ack.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    pass

                await asyncio.sleep(0.4)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                print(f"[Voice Loop Error] {exc}")
                await asyncio.sleep(1.5)

    def notify_audio_ended(self) -> None:
        self._audio_ack.set()
