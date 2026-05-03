"""Subtitle rendering with white text and black outline.

Uses Pillow's ImageFont. Searches for CJK-capable fonts on the system;
falls back to the default bitmap font if none found (no CJK, but won't crash).
"""

from pathlib import Path
from PIL import Image, ImageFont, ImageDraw


_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def _find_font() -> str | None:
    """Find a CJK-capable TrueType font on the system."""
    candidates = [
        # Noto CJK (Linux / Debian)
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        # AR PL UMing (common on Debian)
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        # Common fallbacks
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font at the given size, with caching."""
    cache_key = ("__default__", size)
    font_path = _find_font()

    if font_path:
        cache_key = (font_path, size)

    if cache_key not in _FONT_CACHE:
        if font_path:
            try:
                _FONT_CACHE[cache_key] = ImageFont.truetype(font_path, size)
            except OSError:
                _FONT_CACHE[cache_key] = ImageFont.load_default()
        else:
            _FONT_CACHE[cache_key] = ImageFont.load_default()

    return _FONT_CACHE[cache_key]


def render_subtitle(
    text: str,
    canvas_w: int = 1920,
    canvas_h: int = 1080,
    font_size: int = 40,
    outline_width: int = 3,
    padding_bottom: int = 80,
) -> Image.Image:
    """Render subtitle text as an RGBA image with white fill and black outline.

    Returns a transparent RGBA image sized to fit the text, meant to be
    pasted at bottom-center of the frame.
    """
    font = _get_font(font_size)

    # Measure text
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Add padding for outline
    pad = outline_width * 2 + 4
    img_w = text_w + pad
    img_h = text_h + pad

    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    center_x = img_w / 2
    center_y = img_h / 2

    # Draw black outline at offset positions
    for dx in (-outline_width, 0, outline_width):
        for dy in (-outline_width, 0, outline_width):
            if dx == 0 and dy == 0:
                continue
            draw.text(
                (center_x + dx, center_y + dy),
                text,
                font=font,
                fill=(0, 0, 0, 255),
                anchor="mm",
            )

    # Draw white fill at center
    draw.text(
        (center_x, center_y),
        text,
        font=font,
        fill=(255, 255, 255, 255),
        anchor="mm",
    )

    return img


def clear_font_cache() -> None:
    _FONT_CACHE.clear()
