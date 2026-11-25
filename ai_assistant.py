import os
import time
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI


class AIAssistant:
    """直播间 AI 助播大脑：负责弹幕筛选、冷却限流、调用大模型 API 及违禁词拦截。"""

    def __init__(self, knowledge_path: str = "knowledge.txt") -> None:
        self.enabled = os.getenv("AI_ENABLED", "false").lower() in ("1", "true", "yes")
        self.dry_run = os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")
        self.api_key = os.getenv("LLM_API_KEY", "").strip()
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").strip()
        self.model = os.getenv("LLM_MODEL", "deepseek-chat").strip()
        self.bot_nickname = os.getenv("BOT_NICKNAME", "").strip()
        self.cooldown = float(os.getenv("REPLY_COOLDOWN", "12"))
        self.banned_words = [
            w.strip()
            for w in os.getenv("BANNED_WORDS", "最便宜,全网第一,微信,加V").split(",")
            if w.strip()
        ]

        self.knowledge_path = Path(knowledge_path)
        self._last_reply_ts: float = 0.0
        self._busy: bool = False
        self.client: Optional[AsyncOpenAI] = None

        if self.enabled:
            if not self.api_key:
                print("[AI] 已开启 AI_ENABLED，但未填写 LLM_API_KEY，AI 助播暂不生效。")
                self.enabled = False
            else:
                self.client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
                mode = (
                    "演习模式 (DRY_RUN=true，不真发)"
                    if self.dry_run
                    else "正式发送模式 (DRY_RUN=false)"
                )
                print(
                    f"[AI] 助播已就绪 | 模型: {self.model} | 冷却: {self.cooldown}s | {mode}"
                )

    def _load_knowledge(self) -> str:
        if self.knowledge_path.exists():
            return self.knowledge_path.read_text(encoding="utf-8").strip()
        return "你是直播间热情简短的助播，回复不超过40字，无需回答则输出 SKIP。"

    def should_consider(self, nickname: str, content: str) -> bool:
        """前置轻量规则过滤，节省 API 调用并避免死循环。"""
        if not self.enabled or not self.client:
            return False
        if self._busy:
            return False
        if self.bot_nickname and nickname == self.bot_nickname:
            return False
        text = content.strip()
        if len(text) < 2:
            return False
        if time.time() - self._last_reply_ts < self.cooldown:
            return False
        return True

    def contains_banned_word(self, text: str) -> Optional[str]:
        for word in self.banned_words:
            if word in text:
                return word
        return None

    async def generate_reply(self, nickname: str, content: str) -> Optional[str]:
        """调用大模型生成回复；返回 None 表示跳过不回复。"""
        if not self.should_consider(nickname, content):
            return None

        self._busy = True
        try:
            system_prompt = self._load_knowledge()
            user_prompt = f"观众「{nickname}」发弹幕说：{content}"

            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=80,
                temperature=0.6,
            )
            reply = (resp.choices[0].message.content or "").strip()
            reply = reply.replace("\n", " ").strip()

            if not reply or reply.upper().startswith("SKIP"):
                return None

            hit = self.contains_banned_word(reply)
            if hit:
                print(f"[AI 拦截] 回复命中违禁词「{hit}」，已丢弃: {reply}")
                return None

            if len(reply) > 45:
                reply = reply[:45]

            self._last_reply_ts = time.time()
            return reply
        except Exception as exc:
            print(f"[AI Error] 调用大模型失败: {exc}")
            return None
        finally:
            self._busy = False
