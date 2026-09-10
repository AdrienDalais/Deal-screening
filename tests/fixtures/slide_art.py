"""Raster images for the slide fixture, generated with PIL.

Two of these exist to be *unreadable*.

A real IM carries pages whose numbers live only inside a pasted image,
and a screening tool that silently omits them is worse than one that
refuses: it produces a confident answer with a hole in it. So the fixture
contains content that text extraction genuinely cannot recover, and the
system is expected to report the page as unread rather than skip it.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw


def _font():
    from PIL import ImageFont
    for path in ("/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(path, 40), ImageFont.truetype(path, 26)
        except Exception:
            continue
    return ImageFont.load_default(), ImageFont.load_default()


def unreadable_chart(values: list[tuple[str, float]], title: str) -> bytes:
    """A bar chart rendered as pixels. The numbers are NOT in the PDF.

    Visible to a human, invisible to pypdf. Any pipeline that reports
    this page as empty is wrong; it must report it as unread.
    """
    width, height = 1600, 900
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    big, small = _font()

    draw.text((60, 40), title, fill="black", font=big)
    peak = max(v for _, v in values) or 1.0
    base_y, left, bar_w, gap = 780, 120, 150, 60

    for index, (label, value) in enumerate(values):
        x = left + index * (bar_w + gap)
        bar_h = int((value / peak) * 520)
        draw.rectangle([x, base_y - bar_h, x + bar_w, base_y],
                       fill=(70, 100, 150))
        draw.text((x + 12, base_y - bar_h - 40), f"{value:,.1f}",
                  fill="black", font=small)
        draw.text((x + 40, base_y + 16), label, fill="black", font=small)

    draw.line([left - 30, base_y, width - 60, base_y], fill="black", width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def logo_tile(seed: int) -> bytes:
    """A small coloured tile standing in for a customer logo.

    The real deck's logo wall carries 42 images and 177 characters of
    text. Whatever those logos say is invisible to extraction — which is
    the point of including them.
    """
    palette = [(58, 82, 122), (86, 122, 96), (140, 92, 74), (104, 84, 130),
               (70, 110, 122), (132, 112, 66)]
    image = Image.new("RGB", (96, 48), palette[seed % len(palette)])
    draw = ImageDraw.Draw(image)
    draw.rectangle([4, 4, 91, 43], outline="white", width=2)
    draw.ellipse([10, 14, 30, 34], fill="white")
    draw.rectangle([38, 18, 84, 23], fill="white")
    draw.rectangle([38, 28, 70, 32], fill="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def background_band(width: int = 1920, height: int = 1080) -> bytes:
    """The slide template that appears on nearly every page.

    Present so the fixture reproduces the thing that fooled the first
    version of inspect_pdf: one large image repeated across the deck,
    which is furniture rather than content.
    """
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, 14], fill=(58, 82, 122))
    draw.rectangle([0, height - 46, width, height], fill=(242, 244, 248))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def bullet_marker(seed: int = 0) -> bytes:
    """A 16x16 glyph placed beside each bullet.

    The real deck carries 546 images under 10k pixels — bullets, glyphs
    and icons. They are furniture, but a fixture without them lets
    inspect_pdf draw the wrong conclusion about what the images in a deck
    are for.
    """
    palette = [(58, 82, 122), (110, 134, 170), (86, 122, 96)]
    image = Image.new("RGB", (16, 16), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse([3, 3, 13, 13], fill=palette[seed % len(palette)])
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
