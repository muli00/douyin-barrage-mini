import asyncio
import json
import random
from pathlib import Path
from typing import Any, Dict, List

from playwright.async_api import BrowserContext, Page

# 浏览器导出插件常见的 sameSite 值到 Playwright 标准的映射
SAMESITE_MAP = {
    "strict": "Strict",
    "lax": "Lax",
    "none": "None",
    "no_restriction": "None",
    "unspecified": "Lax",
}

# 抖音 Web 直播间常见的弹幕输入框定位候选
INPUT_SELECTORS = [
    "textarea.webcast-chatroom___textarea",
    '[data-e2e="chat-input"] textarea',
    '[data-e2e="chat-input"]',
    'textarea[placeholder*="聊"]',
    'div[contenteditable="true"]',
]


def normalize_cookies(raw_cookies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把 Cookie-Editor / EditThisCookie 导出的 JSON 清洗为 Playwright 标准格式。"""
    cleaned: List[Dict[str, Any]] = []
    for item in raw_cookies:
        name = item.get("name")
        value = item.get("value")
        domain = item.get("domain")
        if not (name and value is not None and domain):
            continue

        cookie: Dict[str, Any] = {
            "name": str(name),
            "value": str(value),
            "domain": str(domain),
            "path": str(item.get("path") or "/"),
            "httpOnly": bool(item.get("httpOnly", False)),
            "secure": bool(item.get("secure", False)),
        }

        exp = item.get("expires", item.get("expirationDate"))
        if isinstance(exp, (int, float)) and exp > 0:
            cookie["expires"] = float(exp)

        raw_ss = str(item.get("sameSite") or "lax").lower()
        cookie["sameSite"] = SAMESITE_MAP.get(raw_ss, "Lax")

        # Playwright 要求 sameSite="None" 时 secure 必须为 True
        if cookie["sameSite"] == "None":
            cookie["secure"] = True

        cleaned.append(cookie)
    return cleaned


async def inject_cookies_if_exists(
    context: BrowserContext, cookie_path: str = "cookies.json"
) -> int:
    """如果项目根目录存在 cookies.json，则自动注入到浏览器上下文。"""
    path = Path(cookie_path)
    if not path.exists():
        print("[Cookie] 未发现 cookies.json，当前以游客/历史会话模式运行。")
        return 0

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "cookies" in raw:
            raw = raw["cookies"]
        if not isinstance(raw, list):
            print("[Cookie] cookies.json 格式无效（应为 JSON 数组），已跳过。")
            return 0

        cookies = normalize_cookies(raw)
        if cookies:
            await context.add_cookies(cookies)
            print(f"[Cookie] 已成功注入 {len(cookies)} 条登录 Cookie。")
        return len(cookies)
    except Exception as exc:
        print(f"[Cookie Error] 读取或注入 cookies.json 失败: {exc}")
        return 0


class BarrageSender:
    """通过 Playwright 操控抖音直播间网页输入框发送弹幕。"""

    def __init__(self, page: Page) -> None:
        self.page = page
        self._lock = asyncio.Lock()

    async def send(self, text: str) -> bool:
        async with self._lock:
            try:
                # 模拟真人反应与打字延迟
                await asyncio.sleep(random.uniform(1.2, 2.5))

                for selector in INPUT_SELECTORS:
                    locator = self.page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible():
                        await locator.click()
                        await locator.fill(text)
                        await asyncio.sleep(random.uniform(0.3, 0.7))
                        await locator.press("Enter")
                        print(f"[发送成功] {text}")
                        return True

                print("[发送失败] 未在页面找到可见的弹幕输入框（可能尚未登录或触发了验证码）。")
                return False
            except Exception as exc:
                print(f"[发送异常] {exc}")
                return False
