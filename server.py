import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from engine import LiveEngine


def create_app(engine: LiveEngine) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await engine.start()
        yield
        await engine.stop()

    app = FastAPI(title="Douyin AI Live Studio", lifespan=lifespan)

    @app.get("/api/state")
    async def get_state() -> Dict[str, Any]:
        state = engine.build_state()
        state["recent_events"] = list(engine.recent_events)
        return state

    @app.post("/api/config")
    async def update_config(payload: Dict[str, Any]) -> Dict[str, Any]:
        pub = engine.update_config(payload)
        await engine.broadcast_ui(engine.build_state())
        return {"ok": True, "config": pub}

    @app.post("/api/room/connect")
    async def connect_room(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            await engine.connect_room(payload.get("live_url"))
            return {"ok": True, "state": engine.build_state()}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/room/disconnect")
    async def disconnect_room() -> Dict[str, Any]:
        await engine.disconnect_room()
        return {"ok": True, "state": engine.build_state()}

    @app.post("/api/script/generate")
    async def generate_script(payload: Dict[str, Any]) -> Dict[str, Any]:
        product_url = str(payload.get("product_url") or "").strip()
        extra_notes = str(payload.get("extra_notes") or "").strip()
        if not product_url and not extra_notes:
            raise HTTPException(
                status_code=400, detail="请至少填写商品链接或补充商品卖点说明"
            )
        try:
            result = await engine.extract_and_generate_script(product_url, extra_notes)
            return {"ok": True, **result}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/script/save")
    async def save_script(payload: Dict[str, Any]) -> Dict[str, Any]:
        if "pitch_raw" in payload:
            engine.save_pitch_raw(str(payload["pitch_raw"]))
        if "knowledge" in payload and str(payload["knowledge"]).strip():
            engine.ai.save_knowledge(str(payload["knowledge"]))
        await engine.broadcast_ui(engine.build_state())
        return {"ok": True, "line_count": len(engine.load_pitch_lines())}

    @app.post("/api/voice/control")
    async def voice_control(payload: Dict[str, Any]) -> Dict[str, Any]:
        action = payload.get("action")
        if action == "start_pitch":
            engine.update_config({"voice_enabled": True, "voice_pitch_enabled": True})
        elif action == "pause_pitch":
            engine.update_config({"voice_pitch_enabled": False})
        elif action == "jump_pitch":
            idx = int(payload.get("index", 0))
            engine.jump_to_pitch(idx)
        elif action == "interject_voice":
            text = str(payload.get("text") or "").strip()
            if not text:
                raise HTTPException(status_code=400, detail="插播内容不能为空")
            hit = engine.ai.contains_banned_word(text)
            if hit:
                raise HTTPException(
                    status_code=400, detail=f"包含违禁词「{hit}」，已拦截"
                )
            engine.update_config({"voice_enabled": True, "voice_qa_enabled": True})
            await engine.enqueue_voice_qa("导播控场", "手动插播", text)
            await engine.push_event("voice_qa", "导播手动语音插播已入队", text)
        elif action == "send_text":
            text = str(payload.get("text") or "").strip()
            if not text:
                raise HTTPException(status_code=400, detail="发送内容不能为空")
            hit = engine.ai.contains_banned_word(text)
            if hit:
                raise HTTPException(
                    status_code=400, detail=f"包含违禁词「{hit}」，已拦截"
                )
            try:
                await engine.send_manual_text(text)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        await engine.broadcast_ui(engine.build_state())
        return {"ok": True, "state": engine.build_state()}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        engine.ui_clients.add(ws)
        init_payload = engine.build_state()
        init_payload["recent_events"] = list(engine.recent_events)
        await ws.send_text(json.dumps(init_payload, ensure_ascii=False))
        await engine.broadcast_ui(engine.build_state())

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                    if data.get("event") == "audio_ended":
                        engine.notify_audio_ended()
                except Exception:
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            engine.ui_clients.discard(ws)
            await engine.broadcast_ui(engine.build_state())

    web_dir = Path("web")
    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    @app.get("/")
    async def serve_index() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    return app
