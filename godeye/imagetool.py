"""python -m godeye --make-image <image url or file>

Downloads a product photo, removes a plain white/light studio background, trims it and saves
assets/target.png (the picture shown on the dashboard). Needs Pillow: python -m pip install pillow
"""
import io
from collections import deque
from pathlib import Path

from .config import ROOT

OUT = ROOT / "assets" / "target.png"


def _load(src: str):
    from PIL import Image
    if src.startswith("//"):
        src = "https:" + src
    if src.startswith("http"):
        from .fetch import get
        return Image.open(io.BytesIO(get(src).content))
    return Image.open(src)


def make(src: str, tolerance: int = 60, max_height: int = 520) -> Path:
    from PIL import Image, ImageFilter

    im = _load(src).convert("RGBA")
    w, h = im.size
    px = im.load()
    corner = px[0, 0][:3]

    def is_bg(p):
        return all(abs(p[i] - corner[i]) <= tolerance for i in range(3))

    # Flood-fill from every edge pixel so light areas *inside* the product are kept.
    bg = bytearray(w * h)
    q = deque((x, y) for x in range(w) for y in (0, h - 1))
    q.extend((x, y) for y in range(h) for x in (0, w - 1))
    while q:
        x, y = q.popleft()
        i = y * w + x
        if bg[i] or not is_bg(px[x, y]):
            continue
        bg[i] = 1
        if x > 0: q.append((x - 1, y))
        if x < w - 1: q.append((x + 1, y))
        if y > 0: q.append((x, y - 1))
        if y < h - 1: q.append((x, y + 1))

    mask = Image.frombytes("L", (w, h), bytes(0 if b else 255 for b in bg))
    mask = mask.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(0.8))  # trim light fringe, soften edge
    im.putalpha(mask)
    im = im.crop(mask.point(lambda a: 255 if a > 8 else 0).getbbox() or (0, 0, w, h))
    if im.height > max_height:
        im = im.resize((round(im.width * max_height / im.height), max_height), Image.LANCZOS)

    OUT.parent.mkdir(exist_ok=True)
    im.save(OUT, optimize=True)
    return OUT
