import asyncio
import os
from pathlib import Path
from typing import Dict, List, Optional

import edge_tts


async def synthesize_to_file(
    text: str, out_file: Path, voice: str, rate: str = "+8%"
) -> None:
    """使用 edge-tts 合成 MP3，先写临时文件再原子替换，避免播放器读到半截文件。"""
    out_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = out_file.with_suffix(".mp3.tmp")
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(tmp_file))
    tmp_file.replace(out_file)


class VoiceSpeaker:
    """双轨 TTS 语音调度器：优先插播观众弹幕答疑，空闲时按句循环读取 pitch.txt 讲品。"""

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

        if self.enabled:
            print(
                f"[Voice] 🎙️ AI 语音已启用 | 音色: {self.voice_name} ({self.voice_rate}) "
                f"| 循环讲品: {self.pitch_enabled} | 弹幕插播答疑: {self.qa_enabled}"
            )

    def load_pitch_lines(self) -> List[str]:
        """实时读取 pitch.txt（跳过空行和 # 注释行），支持直播中途热修改。"""
        if not self.pitch_path.exists():
            return []
        lines: List[str] = []
        for raw in self.pitch_path.read_text(encoding="utf-8").splitlines():
            s = raw.strip()
            if s and not s.startswith("#"):
                lines.append(s)
        return lines

    async def enqueue_qa(self, nickname: str, question: str, reply_text: str) -> None:
        """将观众弹幕答疑推入高优插播队列。"""
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

    async def _loop(self) -> None:
        # 启动前清理可能残留的旧音频文件
        if self.audio_file.exists():
            self.audio_file.unlink()

        warned_no_player = False
        while True:
            try:
                # 如果上一句 current.mp3 还没被 Mac 端的 afplay 播完删掉，继续等待
                if self.audio_file.exists():
                    await asyncio.sleep(0.25)
                    continue

                kind = None
                speak_text = ""

                # 1. 高优先级：弹幕提问插播答疑
                if self.qa_enabled and not self.qa_queue.empty():
                    item = await self.qa_queue.get()
                    kind = "弹幕答疑"
                    speak_text = item["text"]
                # 2. 低优先级：日常循环讲品短句
                elif self.pitch_enabled:
                    lines = self.load_pitch_lines()
                    if lines:
                        if self.pitch_index >= len(lines):
                            self.pitch_index = 0
                        kind = f"商品讲解 {self.pitch_index + 1}/{len(lines)}"
                        speak_text = lines[self.pitch_index]
                        self.pitch_index = (self.pitch_index + 1) % len(lines)

                if not speak_text:
                    await asyncio.sleep(0.5)
                    continue

                await synthesize_to_file(
                    speak_text,
                    out_file=self.audio_file,
                    voice=self.voice_name,
                    rate=self.voice_rate,
                )
                print(f"[语音播报 · {kind}] {speak_text}")

                # 等待宿主机 play_audio.sh (afplay) 播放完毕并删除 current.mp3
                waited = 0.0
                while self.audio_file.exists():
                    await asyncio.sleep(0.25)
                    waited += 0.25
                    if waited >= 15.0 and not warned_no_player:
                        print(
                            "[Voice 提示] 检测到 audio_out/current.mp3 超过 15 秒未被消费，请确认 Mac 已运行 start_mac_chrome.sh 或 bash play_audio.sh！"
                        )
                        warned_no_player = True

                warned_no_player = False
                # 句间自然呼吸停顿 0.4 秒
                await asyncio.sleep(0.4)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                print(f"[Voice Error] 语音合成或调度异常: {exc}")
                await asyncio.sleep(2.0)

    def start(self) -> None:
        if self.enabled and self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.audio_file.exists():
            self.audio_file.unlink()
