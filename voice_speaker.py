import asyncio
import base64
import os
from pathlib import Path
from typing import Dict, List, Optional

import edge_tts

VOICE_PRESETS = [
    {"id": "zh-CN-XiaoxiaoNeural", "label": "晓晓（普通话·亲切带货女声·推荐）"},
    {"id": "zh-CN-XiaoyiNeural", "label": "晓伊（普通话·活泼甜美女声）"},
    {"id": "zh-CN-YunxiNeural", "label": "云希（普通话·阳光活力男声）"},
    {"id": "zh-HK-HiuMaanNeural", "label": "晓曼（地道粤语·亲切女声）"},
    {"id": "zh-HK-WanLungNeural", "label": "云龙（地道粤语·自然男声）"},
    {"id": "zh-CN-liaoning-XiaobeiNeural", "label": "小北（东北话·热情幽默女声）"},
]


async def synthesize_tts_b64(text: str, voice: str, rate: str = "+8%") -> str:
    """在内存中流式合成 MP3 并返回 Base64 字符串（跨平台前端直接播放，零临时文件）。"""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            buf.extend(chunk["data"])
    if not buf:
        raise RuntimeError("TTS 未返回有效音频流")
    return base64.b64encode(bytes(buf)).decode("ascii")


async def synthesize_to_file(
    text: str, out_file: Path, voice: str, rate: str = "+8%"
) -> None:
    """使用 edge-tts 合成 MP3 到本地文件（兼容本地文件播放模式）。"""
    out_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = out_file.with_suffix(".mp3.tmp")
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(tmp_file))
    tmp_file.replace(out_file)


def parse_pitch_text(raw: str) -> List[str]:
    lines: List[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            lines.append(s)
    return lines


class VoiceSpeaker:
    """保留兼容的本地文件双轨 TTS 调度器（纯命令行模式下使用）。"""

    def __init__(
        self,
        pitch_path: str = "pitch.txt",
        audio_dir: str = "audio_out",
    ) -> None:
        self.enabled = os.getenv("VOICE_ENABLED", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        self.pitch_enabled = os.getenv("VOICE_PITCH_ENABLED", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        self.qa_enabled = os.getenv("VOICE_QA_ENABLED", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        self.voice_name = os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoNeural").strip()
        self.voice_rate = os.getenv("TTS_RATE", "+8%").strip()

        self.pitch_path = Path(pitch_path)
        self.audio_file = Path(audio_dir) / "current.mp3"
        self.qa_queue: asyncio.Queue[Dict[str, str]] = asyncio.Queue(maxsize=30)
        self.pitch_index: int = 0
        self._task: Optional[asyncio.Task] = None

    def load_pitch_lines(self) -> List[str]:
        if not self.pitch_path.exists():
            return []
        return parse_pitch_text(self.pitch_path.read_text(encoding="utf-8"))

    async def enqueue_qa(self, nickname: str, question: str, reply_text: str) -> None:
        if not (self.enabled and self.qa_enabled):
            return
        if self.qa_queue.full():
            try:
                self.qa_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self.qa_queue.put(
            {"nickname": nickname, "question": question, "text": reply_text}
        )
