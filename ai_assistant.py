import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from openai import AsyncOpenAI


class AIAssistant:
    """直播间 AI 助播大脑：支持动态热更新配置、双通道答疑生成与商品口播稿生成。"""

    def __init__(
        self,
        knowledge_path: str = "knowledge.txt",
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.knowledge_path = Path(knowledge_path)
        self._last_reply_ts: float = 0.0
        self._busy: bool = False
        self.client: Optional[AsyncOpenAI] = None

        self.enabled: bool = False
        self.text_reply_enabled: bool = True
        self.dry_run: bool = True
        self.api_key: str = ""
        self.base_url: str = "https://api.deepseek.com"
        self.model: str = "deepseek-chat"
        self.bot_nickname: str = ""
        self.cooldown: float = 12.0
        self.banned_words: list[str] = []

        if config is not None:
            self.apply_config(config)
        else:
            self.apply_config(
                {
                    "ai_enabled": os.getenv("AI_ENABLED", "false").lower()
                    in ("1", "true", "yes"),
                    "text_reply_enabled": os.getenv(
                        "TEXT_REPLY_ENABLED", "true"
                    ).lower()
                    in ("1", "true", "yes"),
                    "dry_run": os.getenv("DRY_RUN", "true").lower()
                    in ("1", "true", "yes"),
                    "llm_api_key": os.getenv("LLM_API_KEY", ""),
                    "llm_base_url": os.getenv(
                        "LLM_BASE_URL", "https://api.deepseek.com"
                    ),
                    "llm_model": os.getenv("LLM_MODEL", "deepseek-chat"),
                    "bot_nickname": os.getenv("BOT_NICKNAME", ""),
                    "reply_cooldown": float(os.getenv("REPLY_COOLDOWN", "12")),
                    "banned_words": os.getenv(
                        "BANNED_WORDS", "最便宜,全网第一,微信,加V"
                    ),
                }
            )

    def apply_config(self, cfg: Dict[str, Any]) -> None:
        """从配置字典热刷新参数与 OpenAI 客户端，无需重启进程。"""
        self.enabled = bool(cfg.get("ai_enabled", False))
        self.text_reply_enabled = bool(cfg.get("text_reply_enabled", True))
        self.dry_run = bool(cfg.get("dry_run", True))
        new_key = str(cfg.get("llm_api_key", "") or "").strip()
        new_url = str(
            cfg.get("llm_base_url", "https://api.deepseek.com") or ""
        ).strip()
        self.model = str(cfg.get("llm_model", "deepseek-chat") or "").strip()
        self.bot_nickname = str(cfg.get("bot_nickname", "") or "").strip()
        self.cooldown = float(cfg.get("reply_cooldown", 12.0))
        raw_banned = cfg.get("banned_words", "最便宜,全网第一,微信,加V")
        if isinstance(raw_banned, list):
            self.banned_words = [str(w).strip() for w in raw_banned if str(w).strip()]
        else:
            self.banned_words = [
                w.strip() for w in str(raw_banned).split(",") if w.strip()
            ]

        if new_key != self.api_key or new_url != self.base_url or self.client is None:
            self.api_key = new_key
            self.base_url = new_url
            self.client = (
                AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
                if self.api_key
                else None
            )

        if self.enabled and not self.api_key:
            print("[AI] 已开启 AI_ENABLED，但尚未配置 LLM_API_KEY（可在网页右上角设置中填写）。")

    def load_knowledge(self) -> str:
        if self.knowledge_path.exists():
            return self.knowledge_path.read_text(encoding="utf-8").strip()
        return "你是直播间热情简短的助播，回复不超过40字，无需回答则输出 SKIP。"

    def save_knowledge(self, content: str) -> None:
        self.knowledge_path.write_text(content.strip() + "\n", encoding="utf-8")

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

    @staticmethod
    def _extract_json(raw: str) -> dict:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        return json.loads(cleaned)

    async def generate_reply(self, nickname: str, content: str) -> Optional[str]:
        """兼容单通道公屏文字回复生成。"""
        dual = await self.generate_dual_reply(
            nickname, content, need_text=True, need_voice=False
        )
        return dual.get("text_reply") if dual else None

    async def generate_dual_reply(
        self,
        nickname: str,
        content: str,
        need_text: bool = True,
        need_voice: bool = True,
    ) -> Optional[Dict[str, str]]:
        """一次请求同时生成公屏文字回复与语音插播口播词；无需回复返回 None。"""
        if not (need_text or need_voice):
            return None
        if not self.should_consider(nickname, content):
            return None

        self._busy = True
        try:
            knowledge = self.load_knowledge()
            banned_str = "、".join(self.banned_words) if self.banned_words else "无"
            system_prompt = (
                f"{knowledge}\n\n"
                "请根据上述人设与知识库评估观众弹幕，并严格只输出一个 JSON 对象（不要任何额外解释）：\n"
                "1. 若弹幕只是闲聊/表情/刷屏无需回答，输出：{\"skip\": true}\n"
                "2. 若需要回答，输出：{\"skip\": false, \"text_reply\": \"公屏简短回复(不超过40字)\", "
                "\"voice_reply\": \"直播间语音点名口播回复(自然亲切，例如：刚看到某某问...，不超过65字)\"}\n"
                f"3. 严禁出现以下违禁词：{banned_str}。"
            )
            user_prompt = f"观众「{nickname}」发弹幕说：{content}"

            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=220,
                temperature=0.6,
            )
            raw = (resp.choices[0].message.content or "").strip()
            if not raw or raw.upper().startswith("SKIP"):
                return None

            data = self._extract_json(raw)
            if data.get("skip"):
                return None

            result: Dict[str, str] = {}
            if need_text:
                t_rep = str(data.get("text_reply") or "").replace("\n", " ").strip()
                hit = self.contains_banned_word(t_rep)
                if hit:
                    print(f"[AI 拦截] 公屏回复命中违禁词「{hit}」，已丢弃: {t_rep}")
                elif t_rep:
                    result["text_reply"] = t_rep[:45]

            if need_voice:
                v_rep = str(data.get("voice_reply") or "").replace("\n", " ").strip()
                hit = self.contains_banned_word(v_rep)
                if hit:
                    print(f"[AI 拦截] 语音回复命中违禁词「{hit}」，已丢弃: {v_rep}")
                elif v_rep:
                    result["voice_reply"] = v_rep[:80]

            if result:
                self._last_reply_ts = time.time()
                return result
            return None
        except Exception as exc:
            print(f"[AI Error] 生成答疑回复失败: {exc}")
            return None
        finally:
            self._busy = False

    async def generate_product_script(
        self, raw_page_text: str, extra_notes: str
    ) -> Dict[str, object]:
        """根据抓取到的商品页文本和补充卖点，生成短句口播讲解稿与知识库条目。"""
        if not self.client:
            if not self.api_key:
                raise RuntimeError("尚未配置 LLM_API_KEY，请先在右上角「系统设置」中填写 API Key。")
            self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

        banned_str = "、".join(self.banned_words) if self.banned_words else "无"
        knowledge = self.load_knowledge()

        system_prompt = (
            "你是资深抖音带货直播口播策划师。请严格依据用户提供的【商品页面提取信息】与【补充说明】创作，绝不虚构未提及的价格、材质或售后承诺。\n"
            f"参考当前直播间人设：\n{knowledge[:500]}\n\n"
            f"严禁出现以下直播违禁词：{banned_str}。\n"
            "请严格只输出如下格式的 JSON 对象（不要 Markdown 代码块外的多余文字）：\n"
            "{\n"
            '  "product_title": "商品简短名称",\n'
            '  "pitch_lines": [\n'
            '    "第1句吸引留人的开场短句（18~35字，适合5秒左右念完）",\n'
            '    "第2句核心面料/功能卖点短句（18~35字）",\n'
            '    "...共生成 10 到 14 句自然衔接、口语化、有节奏感的短句，方便随时插播答疑"\n'
            "  ],\n"
            '  "qa_entry": "- 商品名称：提炼价格、尺码、材质、发货、售后等客观参数摘要（一行或数行，供答疑知识库追加使用）"\n'
            "}"
        )
        user_prompt = (
            f"【商品页面提取信息】：\n{raw_page_text or '（未提供链接或页面无文本，请仅依据下方补充说明生成）'}\n\n"
            f"【主播补充说明/链接号/优惠】：\n{extra_notes or '（无额外补充）'}"
        )

        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1200,
            temperature=0.65,
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = self._extract_json(raw)

        lines = []
        for line in data.get("pitch_lines", []):
            s = str(line).strip()
            if not s:
                continue
            hit = self.contains_banned_word(s)
            if hit:
                s = s.replace(hit, "**")
            lines.append(s)

        return {
            "product_title": str(data.get("product_title") or "直播间主推商品"),
            "pitch_lines": lines,
            "qa_entry": str(data.get("qa_entry") or "").strip(),
        }
