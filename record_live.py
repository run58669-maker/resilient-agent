"""Live screen recording orchestrator.

Layout:
    [ left half: cmd.exe running demo.py ]  [ right half: Chrome TF traces ]

Steps:
  1. Bring the 9222 Chrome tab to TF Request Traces to the front
  2. Position the Chrome window on the right half of the screen via Win32
  3. Spawn a visible cmd.exe titled uniquely, with a 5-second timeout
     before running demo.py — so we have time to position it left half
  4. Start ffmpeg gdigrab recording for `RECORD_S` seconds
  5. Wait until ffmpeg completes
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

# === config ===
ROOT = Path(__file__).parent
VIDEO_DIR = ROOT / "video"
OUT = VIDEO_DIR / "segment_live.mp4"

SCREEN_W = 1920
SCREEN_H = 1080
HALF_W = SCREEN_W // 2
RECORD_S = 75               # ffmpeg recording window — covers prep + demo
DEMO_DELAY_S = 6            # delay before demo.py starts inside the spawned cmd
TITLE = f"ResilientDemo_{int(time.time())}"
PY = r"C:\Users\86150\AppData\Local\Python\pythoncore-3.14-64\python.exe"

# === Win32 ===
user32 = ctypes.windll.user32
SWP_SHOWWINDOW = 0x0040
SW_RESTORE = 9
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2


def enum_windows():
    out: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        out.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return out


def find_window(predicate):
    for hwnd, title in enum_windows():
        if predicate(title):
            return hwnd, title
    return None, None


def place(hwnd, x, y, w, h, topmost=False):
    user32.ShowWindow(hwnd, SW_RESTORE)
    after = HWND_TOPMOST if topmost else 0
    user32.SetWindowPos(hwnd, after, x, y, w, h, SWP_SHOWWINDOW)


def unset_topmost(hwnd):
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | SWP_SHOWWINDOW)


def main():
    # 1. Bring TF Request Traces tab to front via playwright
    print("[1/6] focus TF traces tab via 9222 chrome")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        ctx = browser.contexts[0]
        pg = None
        for t in ctx.pages:
            if "monitoring/request-traces" in t.url:
                pg = t
                break
        if pg is None:
            # navigate any TF tab there
            pg = next((t for t in ctx.pages if "truefoundry.cloud" in t.url), ctx.new_page())
            pg.goto(
                "https://xq-clawd-5615.truefoundry.cloud/monitoring/request-traces",
                wait_until="domcontentloaded",
                timeout=15000,
            )
        pg.bring_to_front()
        time.sleep(0.6)

    # 2. Find Chrome window and move to right half
    print("[2/6] find chrome window + place right half")
    chrome_hwnd, chrome_title = find_window(
        lambda t: "TrueFoundry" in t or "Request Traces" in t or "xq-clawd" in t
    )
    if not chrome_hwnd:
        # fall back to any Chrome window
        chrome_hwnd, chrome_title = find_window(lambda t: t.endswith("Google Chrome"))
    if not chrome_hwnd:
        print("  ERROR: chrome window not found")
        sys.exit(1)
    print(f"  chrome: '{chrome_title}'  hwnd={chrome_hwnd}")
    place(chrome_hwnd, HALF_W, 0, HALF_W, SCREEN_H, topmost=True)

    # 3. Spawn the visible cmd.exe with a delayed demo run
    print(f"[3/6] spawn cmd.exe titled '{TITLE}' (delay {DEMO_DELAY_S}s then demo)")
    win_timeout = r"C:\Windows\System32\timeout.exe"
    inner = (
        f'chcp 65001 >nul && '
        f'title {TITLE} && cd /d {ROOT} && '
        f'echo === Resilient Agent  DevNetwork 2026 === && '
        f'echo Starting in {DEMO_DELAY_S} seconds... && '
        f'{win_timeout} /t {DEMO_DELAY_S} /nobreak >nul && '
        f'"{PY}" -X utf8 demo.py && '
        f'echo === recording window closes shortly ==='
    )
    CREATE_NEW_CONSOLE = 0x00000010
    subprocess.Popen(
        f'cmd /K "{inner}"',
        creationflags=CREATE_NEW_CONSOLE,
        shell=False,
    )

    # 4. Wait for cmd window to appear, then place left half
    print("[4/6] place cmd left half")
    cmd_hwnd = None
    for _ in range(50):
        time.sleep(0.1)
        cmd_hwnd, _ = find_window(lambda t: TITLE in t)
        if cmd_hwnd:
            break
    if not cmd_hwnd:
        print("  ERROR: cmd window not found")
        sys.exit(1)
    place(cmd_hwnd, 0, 0, HALF_W, SCREEN_H, topmost=True)
    time.sleep(0.6)

    # 5. Start ffmpeg recording
    print(f"[5/6] ffmpeg gdigrab {RECORD_S}s -> {OUT.name}")
    VIDEO_DIR.mkdir(exist_ok=True)
    log = (VIDEO_DIR / "ffmpeg_live.log").open("w")
    proc = subprocess.Popen(
        [
            "ffmpeg", "-y",
            "-f", "gdigrab", "-framerate", "30", "-t", str(RECORD_S),
            "-i", "desktop",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(OUT),
        ],
        stdout=log, stderr=log,
    )

    # 6. Wait for ffmpeg to finish then close cmd
    print("[6/6] recording...")
    rc = proc.wait()
    log.close()
    print(f"  ffmpeg rc={rc}")
    # release topmost so windows behave normally again
    unset_topmost(cmd_hwnd)
    unset_topmost(chrome_hwnd)
    # close the demo cmd
    user32.PostMessageW(cmd_hwnd, 0x0010, 0, 0)  # WM_CLOSE
    print(f"\n  → {OUT}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
