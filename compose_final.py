"""Compose final submission video: PIL title slides + trimmed live demo capture.

Layout:
    0:00–0:04   title slide
    0:04–0:08   challenge prompt slide
    0:08–0:33   live split-screen demo (trimmed)
    0:33–0:39   "100% success under chaos" outro
    0:39–0:42   thanks card

Total ~42s.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
VIDEO_DIR = ROOT / "video"
LIVE = VIDEO_DIR / "segment_live.mp4"
SLIDES = VIDEO_DIR / "slides"
OUTPUT = VIDEO_DIR / "submission.mp4"

W, H = 1920, 1080
FPS = 30
BG = (12, 14, 18)
FG = (220, 222, 230)
DIM = (110, 115, 125)
ACC = (255, 180, 90)


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in (
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\CascadiaCode.ttf",
    ):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def slide(text: str, subtitle: str = "", out_path: Path = None) -> Path:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_big = font(82)
    f_sub = font(36)
    tw = d.textlength(text, font=f_big)
    d.text(((W - tw) / 2, 420), text, font=f_big, fill=FG)
    d.line([(W / 2 - 220, 530), (W / 2 + 220, 530)], fill=ACC, width=3)
    if subtitle:
        sw = d.textlength(subtitle, font=f_sub)
        d.text(((W - sw) / 2, 560), subtitle, font=f_sub, fill=DIM)
    img.save(out_path)
    return out_path


def make_slide_video(image_path: Path, seconds: float, out: Path) -> Path:
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-c:v", "libx264", "-t", str(seconds), "-pix_fmt", "yuv420p",
        "-vf", f"scale={W}:{H}", "-r", str(FPS),
        str(out),
    ], check=True, capture_output=True)
    return out


def trim_live(start: float, length: float, out: Path) -> Path:
    """Trim the live capture and re-encode so concat works cleanly."""
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start), "-i", str(LIVE),
        "-t", str(length),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-vf", f"scale={W}:{H}", "-r", str(FPS),
        "-an",
        str(out),
    ], check=True, capture_output=True)
    return out


def concat(parts: list[Path], out: Path) -> None:
    list_file = VIDEO_DIR / "concat.txt"
    list_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts))
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out),
    ], check=True, capture_output=True)


def main() -> None:
    SLIDES.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []

    # Slide 1 — title
    s1_png = slide(
        "Resilient Agent",
        "DevNetwork 2026  ·  TrueFoundry  ·  Resilient Agents track",
        SLIDES / "s1.png",
    )
    parts.append(make_slide_video(s1_png, 4.0, SLIDES / "s1.mp4"))

    # Slide 2 — challenge prompt
    s2_png = slide(
        "How does your agent behave",
        'when an LLM server "errors out or browns out"?',
        SLIDES / "s2.png",
    )
    parts.append(make_slide_video(s2_png, 4.0, SLIDES / "s2.mp4"))

    # Live demo trimmed: start a bit before the countdown ends, end after scorecard
    parts.append(trim_live(start=4.0, length=25.0, out=SLIDES / "live.mp4"))

    # Outro 1
    s3_png = slide(
        "100% success under chaos",
        "p95 latency < 2s   ·   MTTR ~660ms   ·   Fallback survives gateway brownout",
        SLIDES / "s3.png",
    )
    parts.append(make_slide_video(s3_png, 5.0, SLIDES / "s3.mp4"))

    # Outro 2
    s4_png = slide(
        "Built for TrueFoundry",
        "github.com/<your-repo>",
        SLIDES / "s4.png",
    )
    parts.append(make_slide_video(s4_png, 3.0, SLIDES / "s4.mp4"))

    concat(parts, OUTPUT)
    size_kb = OUTPUT.stat().st_size // 1024
    # query duration
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(OUTPUT)],
        capture_output=True, text=True,
    ).stdout.strip()
    print(f"\n  → {OUTPUT}  ({size_kb} KB, {dur}s)")


if __name__ == "__main__":
    main()
