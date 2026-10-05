"""
WittyWhispers quote image generator (100% free: Python + Pillow only).

Setup:
    pip install pillow

Usage:
    1. Put quotes in quotes.json, e.g.
       [{"text": "Be the calm in your own chaos.", "category": "motivation"}]
    2. (Optional) drop .ttf fonts from Google Fonts into a ./fonts folder.
    3. python quote_maker.py
    Images are saved to ./output (feed 1080x1080 and story 1080x1920).
"""
import json
import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HANDLE = "@wittywhispers"
SIZES = {"feed": (1080, 1080), "story": (1080, 1920)}

# (top color, bottom color, text color)
PALETTES = [
    ((255, 154, 158), (250, 208, 196), (60, 20, 40)),
    ((30, 30, 60), (90, 60, 140), (255, 255, 255)),
    ((255, 236, 210), (252, 182, 159), (70, 35, 20)),
    ((17, 153, 142), (56, 239, 125), (10, 40, 30)),
    ((25, 25, 25), (60, 60, 60), (255, 220, 120)),
    ((161, 140, 209), (251, 194, 235), (40, 20, 70)),
    ((255, 183, 94), (237, 143, 3), (50, 25, 0)),
]

FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
]


def find_fonts():
    fonts = [str(p) for p in Path("fonts").glob("*.ttf")] if Path("fonts").exists() else []
    return fonts or [f for f in FALLBACK_FONTS if Path(f).exists()]


def load_font(path, size):
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)
    return img


def fit_text(draw, text, font_path, max_w, max_h):
    """Find the largest font size where wrapped text fits the box."""
    for size in range(110, 28, -4):
        font = load_font(font_path, size)
        chars = max(8, int(max_w / (size * 0.52)))
        lines = textwrap.wrap(text, width=chars)
        spacing = int(size * 0.35)
        widths = [draw.textlength(line, font=font) for line in lines]
        height = len(lines) * size + (len(lines) - 1) * spacing
        if max(widths) <= max_w and height <= max_h:
            return font, lines, spacing, height
    font = load_font(font_path, 28)
    lines = textwrap.wrap(text, width=30)
    return font, lines, 10, len(lines) * 38


def make_image(text, kind, font_path, palette):
    size = SIZES[kind]
    w, h = size
    top, bottom, fg = palette
    img = gradient(size, top, bottom)
    draw = ImageDraw.Draw(img)

    box_w, box_h = int(w * 0.78), int(h * 0.60)
    font, lines, spacing, text_h = fit_text(draw, text, font_path, box_w, box_h)

    y = (h - text_h) // 2
    for line in lines:
        lw = draw.textlength(line, font=font)
        draw.text(((w - lw) / 2, y), line, font=font, fill=fg)
        y += font.size + spacing

    # small accent line + watermark
    draw.line([(w * 0.42, h * 0.86), (w * 0.58, h * 0.86)], fill=fg, width=3)
    wm_font = load_font(font_path, 34)
    wm_w = draw.textlength(HANDLE, font=wm_font)
    draw.text(((w - wm_w) / 2, h * 0.88), HANDLE, font=wm_font, fill=fg)
    return img


def main():
    quotes = json.loads(Path("quotes.json").read_text(encoding="utf-8"))
    fonts = find_fonts() or [None]
    out = Path("output")
    out.mkdir(exist_ok=True)

    for i, q in enumerate(quotes, 1):
        font_path = random.choice(fonts)
        palette = random.choice(PALETTES)
        for kind in SIZES:
            img = make_image(q["text"], kind, font_path, palette)
            img.save(out / f"{i:03d}_{q.get('category', 'quote')}_{kind}.png")
        print(f"made {i}/{len(quotes)}")


if __name__ == "__main__":
    main()
