"""Render the submission video from captured demo output + screenshots.

No screen capture — every frame is generated deterministically by PIL so the
video is reproducible regardless of host machine, theme, or window focus.

Output: video/submission.mp4
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
VIDEO_DIR = ROOT / "video"
FRAMES_DIR = VIDEO_DIR / "frames"
DEMO_OUT = VIDEO_DIR / "demo_stdout.txt"
TRACES_PNG = Path(r"C:\Users\86150\Desktop\tf_traces_real.png")
OUTPUT = VIDEO_DIR / "submission.mp4"

W, H = 1920, 1080
FPS = 30

BG = (12, 14, 18)
FG = (220, 222, 230)
DIM = (110, 115, 125)
ACC = (255, 180, 90)
OK = (140, 220, 140)
ERR = (240, 110, 120)
ACC2 = (130, 180, 255)

# Try common monospace fonts
def font(size: int) -> ImageFont.FreeTypeFont:
    for p in (
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\CascadiaCode.ttf",
        r"C:\Windows\Fonts\CascadiaMono.ttf",
    ):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def make_frame() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    return img


def draw_title_slide(text: str, subtitle: str) -> Image.Image:
    img = make_frame()
    d = ImageDraw.Draw(img)
    f_big = font(72)
    f_sub = font(36)
    # title centred
    tw = d.textlength(text, font=f_big)
    d.text(((W - tw) / 2, 380), text, font=f_big, fill=FG)
    sw = d.textlength(subtitle, font=f_sub)
    d.text(((W - sw) / 2, 500), subtitle, font=f_sub, fill=DIM)
    # accent line
    d.line([(W / 2 - 200, 470), (W / 2 + 200, 470)], fill=ACC, width=3)
    return img


def colour_for_line(line: str):
    if "═══" in line:
        return ACC
    if "OK via" in line or "─── Resilience Scorecard" in line:
        return OK
    if "fail" in line.lower() or "FAIL" in line or "APIError" in line or "APIConnection" in line:
        return ERR
    if "breaker OPEN" in line:
        return ERR
    if "by target" in line or line.lstrip().startswith(("tfy-", "raw-")):
        return ACC2
    if line.lstrip().startswith("└─"):
        return DIM
    return FG


def draw_terminal_lines(lines: list[str], highlight_last: int = 0) -> Image.Image:
    img = make_frame()
    d = ImageDraw.Draw(img)
    f_term = font(24)
    # window chrome
    d.rectangle([(80, 60), (W - 80, 120)], fill=(28, 30, 34))
    d.ellipse([(110, 80), (130, 100)], fill=(240, 100, 100))
    d.ellipse([(140, 80), (160, 100)], fill=(240, 200, 100))
    d.ellipse([(170, 80), (190, 100)], fill=(140, 220, 140))
    d.text((220, 80), "demo.py — Resilient Agent (DevNetwork 2026)", font=font(22), fill=DIM)
    # body
    d.rectangle([(80, 120), (W - 80, H - 80)], fill=(20, 22, 26))
    y = 150
    n = len(lines)
    for i, line in enumerate(lines):
        if y > H - 110:
            break
        col = colour_for_line(line)
        # dim older lines, brighten newest
        if highlight_last and i < n - highlight_last:
            r, g, b = col
            col = (int(r * 0.55), int(g * 0.55), int(b * 0.55))
        d.text((110, y), line[:170], font=f_term, fill=col)
        y += 32
    return img


def draw_image_full(path: Path, caption: str = "") -> Image.Image:
    img = make_frame()
    if path.exists():
        src = Image.open(path).convert("RGB")
        sw, sh = src.size
        ratio = min((W - 160) / sw, (H - 240) / sh)
        nw, nh = int(sw * ratio), int(sh * ratio)
        src = src.resize((nw, nh), Image.LANCZOS)
        img.paste(src, ((W - nw) // 2, 160))
    d = ImageDraw.Draw(img)
    f_cap = font(36)
    if caption:
        cw = d.textlength(caption, font=f_cap)
        d.text(((W - cw) / 2, 80), caption, font=f_cap, fill=ACC)
    return img


def chunk_demo(text: str) -> list[list[str]]:
    """Split demo stdout into 4 logical chunks (intro retries, then 3 scenarios)."""
    lines = text.splitlines()
    # find ═══ markers (scenario headers)
    chunks: list[list[str]] = []
    current: list[str] = []
    for ln in lines:
        if "══════" in ln:
            if current:
                chunks.append(current)
                current = []
        current.append(ln)
    if current:
        chunks.append(current)
    return chunks


def save_frames(frames: list[tuple[Image.Image, float]], start_idx: int = 0) -> int:
    """Save (image, hold_seconds) pairs as numbered frames. Returns next index."""
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    idx = start_idx
    for img, hold in frames:
        n = int(hold * FPS)
        for _ in range(n):
            img.save(FRAMES_DIR / f"frame_{idx:06d}.png")
            idx += 1
    return idx


def main() -> None:
    if not DEMO_OUT.exists():
        print(f"ERROR: missing {DEMO_OUT} — run demo.py with stdout redirected first")
        sys.exit(1)

    # wipe old frames
    if FRAMES_DIR.exists():
        for p in FRAMES_DIR.iterdir():
            p.unlink()

    stdout_text = DEMO_OUT.read_text(encoding="utf-8", errors="replace")
    chunks = chunk_demo(stdout_text)
    print(f"demo split into {len(chunks)} chunks")

    seq: list[tuple[Image.Image, float]] = []

    # Act 1 — title (4s)
    seq.append((draw_title_slide(
        "Resilient Agent",
        "DevNetwork 2026  ·  TrueFoundry  ·  Resilient Agents track",
    ), 4.0))
    seq.append((draw_title_slide(
        "How does your agent behave",
        'when an LLM server "errors out or browns out"?',
    ), 4.0))

    # Act 2 — demo terminal, scenario by scenario
    # build accumulating-line frames so the viewer can read
    for ci, chunk in enumerate(chunks):
        # hold whole chunk for ~ (lines * 0.7s)
        all_lines = chunk
        # show progressive reveal: 1, 4, 8, 12... lines visible
        step = 4
        for end in range(step, len(all_lines) + step, step):
            visible = all_lines[:end]
            seq.append((draw_terminal_lines(visible, highlight_last=step), 0.9))
        # then hold full chunk 2.5s
        seq.append((draw_terminal_lines(all_lines, highlight_last=0), 2.5))

    # Act 3 — TF traces screenshot (8s)
    seq.append((draw_image_full(TRACES_PNG, "Every attempt visible in TrueFoundry Request Traces"), 8.0))

    # Outro slide (3s)
    seq.append((draw_title_slide(
        "100% success rate under chaos",
        "p95 latency < 2s   ·   MTTR ~660ms   ·   Fallback survives gateway brownout",
    ), 5.0))
    seq.append((draw_title_slide(
        "Thanks for watching",
        "github.com/<your-repo>   ·   built for TrueFoundry @ DevNetwork 2026",
    ), 3.0))

    next_idx = save_frames(seq)
    print(f"wrote {next_idx} frames")

    # encode with ffmpeg
    cmd = [
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", str(FRAMES_DIR / "frame_%06d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "medium", "-crf", "22",
        str(OUTPUT),
    ]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"\n  → {OUTPUT}  ({OUTPUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
