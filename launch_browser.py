#!/usr/bin/env python3
"""跨平台独立助播浏览器启动器（零第三方依赖，原生支持 macOS / Windows / Linux）。"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


def find_chromium_binary() -> Optional[str]:
    system = platform.system()

    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for p in candidates:
            if os.path.exists(p):
                return p

    elif system == "Windows":
        env_dirs = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        rel_paths = [
            r"Google\Chrome\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe",
        ]
        for base in env_dirs:
            if not base:
                continue
            for rel in rel_paths:
                full = os.path.join(base, rel)
                if os.path.exists(full):
                    return full

    for cmd in ("google-chrome", "microsoft-edge", "chromium", "chromium-browser", "chrome", "msedge"):
        found = shutil.which(cmd)
        if found:
            return found

    return None


def resolve_profile_dir(base_dir: Path) -> Path:
    """优先沿用已有的 mac_chrome_profile 登录态目录，新环境统一使用 browser_profile。"""
    legacy_dir = base_dir / "mac_chrome_profile"
    if legacy_dir.exists():
        return legacy_dir
    new_dir = base_dir / "browser_profile"
    new_dir.mkdir(parents=True, exist_ok=True)
    return new_dir


def main() -> None:
    port = int(os.environ.get("CHROME_DEBUG_PORT", "9222"))
    target_url = sys.argv[1] if len(sys.argv) > 1 else "https://live.douyin.com/"
    binary = find_chromium_binary()
    if not binary:
        print(
            "[Browser Error] 未在当前系统找到 Google Chrome 或 Microsoft Edge，请先安装其中任意一款浏览器。"
        )
        sys.exit(1)

    base_dir = Path(__file__).resolve().parent
    profile_dir = resolve_profile_dir(base_dir)

    print(f"[Browser] 检测到系统: {platform.system()} | 浏览器: {binary}")
    print(f"[Browser] 调试端口: 127.0.0.1:{port}")
    print(f"[Browser] 独立登录目录: {profile_dir}（与你日常使用的浏览器完全隔离）")
    print("[Browser] 首次打开请在弹出的窗口中扫码登录助播小号，运行期间保持该窗口开启即可。")

    cmd = [
        binary,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        target_url,
    ]
    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Browser] 已关闭助播浏览器窗口。")
