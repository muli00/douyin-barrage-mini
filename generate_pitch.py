"""喂入商品链接（或卖点说明），自动借用已登录的 Mac Chrome 提取页面参数，由 AI 生成口播稿写入 pitch.txt 并同步追加到 knowledge.txt。"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

from ai_assistant import AIAssistant
from main import resolve_cdp_ws_endpoint


async def extract_page_info(cdp_url: str, product_url: str) -> str:
    async with async_playwright() as p:
        if cdp_url:
            ws_ep = resolve_cdp_ws_endpoint(cdp_url)
            print(f"[Generate] 正在通过已登录的 Mac Chrome 打开商品链接...")
            browser = await p.chromium.connect_over_cdp(ws_ep)
            context = (
                browser.contexts[0] if browser.contexts else await browser.new_context()
            )
            page = await context.new_page()
            try:
                await page.goto(product_url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(3.5)
                title = await page.title()
                body = await page.evaluate(
                    "() => document.body ? document.body.innerText : ''"
                )
            finally:
                await page.close()
        else:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                page = await browser.new_page()
                await page.goto(product_url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(3.5)
                title = await page.title()
                body = await page.evaluate(
                    "() => document.body ? document.body.innerText : ''"
                )
            finally:
                await browser.close()

    compact = "\n".join(line.strip() for line in body.splitlines() if line.strip())
    return f"页面标题：{title}\n页面可见文本摘录：\n{compact[:2500]}"


async def main() -> None:
    load_dotenv(override=False)
    product_url = sys.argv[1].strip() if len(sys.argv) > 1 else os.getenv("PRODUCT_URL", "").strip()
    extra_notes = sys.argv[2].strip() if len(sys.argv) > 2 else os.getenv("PRODUCT_NOTES", "").strip()

    if not product_url and not extra_notes:
        print(
            '用法: docker compose run --rm douyin python -u generate_pitch.py "商品链接" "补充卖点/价格说明(可选)"'
        )
        sys.exit(1)

    raw_text = ""
    if product_url and product_url.startswith(("http://", "https://")):
        cdp_url = os.getenv("CDP_URL", "").strip()
        raw_text = await extract_page_info(cdp_url, product_url)
        print(f"[Generate] 已提取页面信息（长度 {len(raw_text)} 字），正在请求 AI 生成口播讲解稿...")
    else:
        # 若第一个参数不是网址，直接当作卖点文字说明
        extra_notes = f"{product_url} {extra_notes}".strip()
        print("[Generate] 正在根据卖点说明请求 AI 生成口播讲解稿...")

    ai = AIAssistant(knowledge_path="knowledge.txt")
    result = await ai.generate_product_script(raw_text, extra_notes)
    lines = result.get("pitch_lines", [])
    if not lines:
        raise RuntimeError("AI 未返回有效的口播短句，请重试。")

    header = (
        f"# 商品口播讲解稿：{result.get('product_title', '')}\n"
        "# 每行一句短话，直播运行期间可直接编辑保存（即时热生效）\n\n"
    )
    Path("pitch.txt").write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"[Generate] ✅ 已写入 pitch.txt（共 {len(lines)} 句短口播稿）！")

    qa_entry = str(result.get("qa_entry") or "").strip()
    if qa_entry:
        cur_k = ai.load_knowledge()
        if qa_entry not in cur_k:
            ai.save_knowledge(f"{cur_k}\n{qa_entry}")
            print(f"[Generate] ✅ 已同步将商品参数追加进 knowledge.txt：\n  {qa_entry}")


if __name__ == "__main__":
    asyncio.run(main())
