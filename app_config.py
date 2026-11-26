import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv


def _env_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes")


def mask_secret(secret: str) -> str:
    s = (secret or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "****"
    return f"{s[:3]}****{s[-4:]}"


class AppConfig:
    """统一配置中心：读写 config.json，首次自动继承 .env，支持前端界面热修改保存。"""

    def __init__(self, config_path: str = "config.json") -> None:
        load_dotenv(override=False)
        self.path = Path(config_path)
        self.data: Dict[str, Any] = self._build_defaults_from_env()
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    self.data.update(saved)
            except Exception as exc:
                print(f"[Config] 读取 {self.path} 失败，使用默认配置: {exc}")
        else:
            # 首次运行自动将 .env 初始化持久化到 config.json
            self.save()

    @staticmethod
    def _build_defaults_from_env() -> Dict[str, Any]:
        return {
            "live_url": os.getenv("LIVE_URL", "https://live.douyin.com/").strip(),
            "only_chat": _env_bool("ONLY_CHAT", True),
            "cdp_url": os.getenv("CDP_URL", "http://host.docker.internal:9222").strip(),
            "headless": _env_bool("HEADLESS", True),
            "ai_enabled": _env_bool("AI_ENABLED", True),
            "text_reply_enabled": _env_bool("TEXT_REPLY_ENABLED", True),
            "dry_run": _env_bool("DRY_RUN", True),
            "voice_enabled": _env_bool("VOICE_ENABLED", True),
            "voice_pitch_enabled": _env_bool("VOICE_PITCH_ENABLED", False),
            "voice_qa_enabled": _env_bool("VOICE_QA_ENABLED", True),
            "tts_voice": os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoNeural").strip(),
            "tts_rate": os.getenv("TTS_RATE", "+8%").strip(),
            "llm_base_url": os.getenv("LLM_BASE_URL", "https://api.deepseek.com").strip(),
            "llm_api_key": os.getenv("LLM_API_KEY", "").strip(),
            "llm_model": os.getenv("LLM_MODEL", "deepseek-chat").strip(),
            "bot_nickname": os.getenv("BOT_NICKNAME", "").strip(),
            "reply_cooldown": float(os.getenv("REPLY_COOLDOWN", "12")),
            "banned_words": os.getenv(
                "BANNED_WORDS", "最便宜,全网第一,绝对,微信,加V,私信我"
            ).strip(),
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def update(self, patch: Dict[str, Any]) -> None:
        for k, v in patch.items():
            if k == "llm_api_key":
                # 前端若留空或传回含 **** 的掩码，则保持原密钥不变
                s = str(v or "").strip()
                if not s or "****" in s:
                    continue
                self.data[k] = s
            elif k == "reply_cooldown":
                try:
                    self.data[k] = max(1.0, float(v))
                except (TypeError, ValueError):
                    pass
            elif k in self.data:
                self.data[k] = v
        self.save()

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def to_public_dict(self) -> Dict[str, Any]:
        """返回给前端的安全字典（隐藏明文 API Key）。"""
        pub = dict(self.data)
        raw_key = str(pub.pop("llm_api_key", "") or "")
        pub["has_api_key"] = bool(raw_key)
        pub["llm_api_key_masked"] = mask_secret(raw_key)
        return pub
