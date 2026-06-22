#!/usr/bin/env python3
"""
Generate PNG test files via PIL:
- images/sample-transparent.png — 256x256 RGBA, alpha=0 (for I14 verify)
- images/landscape.png — 1536x1024 RGB (for I30 verify)
- images/portrait.png — 1024x1536 RGB (for I30 verify)
- images/sample.png — 512x512 RGB with text (fallback if Unsplash download fails for I2/F-PM6)
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Output base dir: first CLI arg (e.g. the target plan's test-data/), else current dir.
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
IMG = ROOT / "images"
IMG.mkdir(parents=True, exist_ok=True)


def make_transparent():
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    img.save(IMG / "sample-transparent.png", "PNG")
    print(f"✓ {IMG/'sample-transparent.png'} (256x256 RGBA alpha=0)")


def gradient(size, name, orientation):
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        for x in range(w):
            r = int(255 * x / w)
            g = int(255 * y / h)
            b = 128
            px[x, y] = (r, g, b)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 60)
    except OSError:
        font = ImageFont.load_default()
    label = f"{orientation} {w}x{h}"
    bbox = draw.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((w - tw) / 2, (h - th) / 2), label, fill=(255, 255, 255), font=font)
    img.save(IMG / name, "PNG")
    print(f"✓ {IMG/name} ({w}x{h} RGB gradient + label)")


def make_sample_fallback():
    """Sample 512x512 — used if Unsplash download fails."""
    target = IMG / "sample.png"
    if target.exists() and target.stat().st_size > 1024:
        print(f"… {target} already exists, skipping fallback generation")
        return
    img = Image.new("RGB", (512, 512), (60, 90, 130))
    draw = ImageDraw.Draw(img)
    for y in range(0, 512, 32):
        draw.line([(0, y), (512, y)], fill=(100, 130, 170), width=1)
    for x in range(0, 512, 32):
        draw.line([(x, 0), (x, 512)], fill=(100, 130, 170), width=1)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.text((100, 220), "Citeck", fill=(220, 230, 240), font=font)
    img.save(target, "PNG")
    print(f"✓ {target} (fallback 512x512 grid + text)")


if __name__ == "__main__":
    make_transparent()
    gradient((1536, 1024), "landscape.png", "landscape")
    gradient((1024, 1536), "portrait.png", "portrait")
    make_sample_fallback()
    print("Done.")
