#!/usr/bin/env python3
"""
Generate pdf/sample-large.pdf — большой PDF (>2 MB) для F10/S9 (file-size limit).
Подход: множество страниц с большими PNG-картинками.

Dependencies:
  pip install reportlab pillow
"""
from pathlib import Path
import io
import sys

from PIL import Image, ImageDraw, ImageFont

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Image as RLImage, PageBreak
    from reportlab.lib.utils import ImageReader
except ImportError:
    raise SystemExit("reportlab not installed — pip install reportlab")

# Output base dir: first CLI arg (e.g. the target plan's test-data/), else current dir.
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
OUT = ROOT / "pdf" / "sample-large.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)


def make_page_image(idx: int) -> Image.Image:
    """Create a 1240x1754 RGB image with random-ish content to inflate PDF size."""
    img = Image.new("RGB", (1240, 1754))
    px = img.load()
    for y in range(0, 1754, 4):
        for x in range(0, 1240, 4):
            r = (x * 7 + idx * 31) % 256
            g = (y * 11 + idx * 41) % 256
            b = ((x + y) * 13 + idx * 53) % 256
            for dy in range(4):
                for dx in range(4):
                    if x + dx < 1240 and y + dy < 1754:
                        px[x + dx, y + dy] = (r, g, b)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 96)
    except OSError:
        font = ImageFont.load_default()
    draw.text((400, 800), f"Page {idx+1}", fill="white", font=font)
    return img


def make_doc():
    return SimpleDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )


def main():
    target_size_bytes = 2 * 1024 * 1024 + 256 * 1024  # 2.25 MB target
    pages_built = []  # list of bytes
    pages = 0
    while True:
        pages += 1
        img = make_page_image(pages - 1)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=92)
        buf.seek(0)
        pages_built.append(buf.getvalue())

        # Rebuild & check size every 2 pages
        if pages >= 4 and pages % 2 == 0:
            doc = make_doc()
            story = []
            for i, raw in enumerate(pages_built):
                story.append(RLImage(io.BytesIO(raw), width=15 * cm, height=21 * cm))
                if i < len(pages_built) - 1:
                    story.append(PageBreak())
            doc.build(story)
            sz = OUT.stat().st_size
            if sz >= target_size_bytes:
                print(f"✓ {OUT} ({pages} pages, {sz/1024/1024:.2f} MB)")
                return
        if pages > 30:
            print(f"⚠ {OUT} stopped at {pages} pages, {OUT.stat().st_size/1024/1024:.2f} MB (manually adjust quality)")
            return


if __name__ == "__main__":
    main()
