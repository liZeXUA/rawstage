"""Subtitle rendering with rich text support.

Supports per-span styling: color, size, italic, underline, bold.
Spans are concatenated horizontally with baseline alignment.
Uses Pillow's ImageFont. Searches for CJK-capable fonts on the system;
falls back to the default bitmap font if none found.
"""

from pathlib import Path
from PIL import Image, ImageFont, ImageDraw

from rawstage.parser.models import SubtitleData, SubtitleSpan


_FONT_CACHE: dict[tuple[str | None, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def _find_font() -> str | None:
    """Find a CJK-capable TrueType font on the system."""
    candidates = [
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        # Noto CJK (Linux)
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def _get_font(size: int, font_path: str | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font at the given size, with caching."""
    cache_key = (font_path, size)

    if cache_key not in _FONT_CACHE:
        path = font_path or _find_font()
        if path:
            try:
                _FONT_CACHE[cache_key] = ImageFont.truetype(path, size)
            except OSError:
                _FONT_CACHE[cache_key] = ImageFont.load_default()
        else:
            _FONT_CACHE[cache_key] = ImageFont.load_default()

    return _FONT_CACHE[cache_key]


def render_subtitle(
    subtitle: SubtitleData,
    canvas_w: int = 1920,
    canvas_h: int = 1080,
    padding_bottom: int = 80,
) -> Image.Image:
    """Render a SubtitleData as an RGBA image.

    Returns a transparent RGBA image meant to be pasted at bottom-center
    of the frame. Handles mixed styles within a single subtitle line.
    """
    if not subtitle.spans:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    # Render each span independently
    span_images: list[Image.Image] = []
    for span in subtitle.spans:
        span_img = _render_span(span, subtitle)
        span_images.append(span_img)

    if not span_images:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    # Concatenate horizontally, centered vertically
    total_w = sum(img.width for img in span_images)
    max_h = max(img.height for img in span_images)

    combined = Image.new("RGBA", (total_w, max_h), (0, 0, 0, 0))
    x = 0
    for img in span_images:
        y = (max_h - img.height) // 2
        combined.paste(img, (x, y), img)
        x += img.width

    return combined


def _render_span(span: SubtitleSpan, data: SubtitleData) -> Image.Image:
    """Render a single span with outline, optional italic/bold/underline."""
    font = _get_font(span.font_size, span.font_path)

    # Measure text
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    text_w = int(draw.textlength(span.text, font=font))
    bbox = draw.textbbox((0, 0), span.text, font=font, anchor="lt")
    text_h = bbox[3] - bbox[1]

    if text_w <= 0 or text_h <= 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    ow = data.outline_width
    # Extra padding for bold offsets, italic shear, underline
    pad_w = ow * 2 + 6
    pad_h = ow * 2 + 6
    if span.italic:
        pad_w += int(text_h * 0.35)
    if span.underline:
        pad_h += 4

    img_w = text_w + pad_w
    img_h = text_h + pad_h
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    tx = img_w / 2
    ty = img_h / 2

    # 1. Outline: draw text at all offsets in outline color
    for dx in range(-ow, ow + 1):
        for dy in range(-ow, ow + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((tx + dx, ty + dy), span.text, font=font,
                      fill=data.outline_color, anchor="mm")

    # 2. Fill with optional bold (draw at slight horizontal offsets)
    if span.bold:
        for bx in (-1, 0, 1):
            draw.text((tx + bx, ty), span.text, font=font,
                      fill=span.color, anchor="mm")
    else:
        draw.text((tx, ty), span.text, font=font,
                  fill=span.color, anchor="mm")

    # 3. Italic via shear transform
    if span.italic:
        img = _apply_italic(img)

    # 4. Underline
    if span.underline:
        img = _draw_underline(img, span, data)

    return img


def _apply_italic(img: Image.Image) -> Image.Image:
    """Apply a horizontal shear to simulate italic text."""
    shear = 0.35
    w, h = img.size
    new_w = int(w + h * shear)
    result = Image.new("RGBA", (new_w, h), (0, 0, 0, 0))
    # Copy with progressive horizontal offset per row
    for y in range(h):
        offset = int((h - y) * shear)
        if offset < 0:
            offset = 0
        row = img.crop((0, y, w, y + 1))
        paste_x = offset
        if paste_x + w > new_w:
            row = row.crop((0, 0, new_w - paste_x, 1))
        if row.width > 0:
            result.paste(row, (paste_x, y))
    return result


def _draw_underline(img: Image.Image, span: SubtitleSpan,
                    data: SubtitleData) -> Image.Image:
    """Draw an underline beneath the text."""
    # Find the bottom of non-transparent content
    alpha = img.getchannel("A")
    # Scan from bottom to find where content ends
    bottom = img.height
    for y in range(img.height - 1, -1, -1):
        row_alpha = alpha.crop((0, y, img.width, y + 1))
        if row_alpha.getextrema()[1] > 0:
            bottom = y
            break

    line_y = bottom + data.outline_width + 2
    if line_y >= img.height:
        # Extend image
        new_img = Image.new("RGBA", (img.width, line_y + 3), (0, 0, 0, 0))
        new_img.paste(img, (0, 0), img)
        img = new_img

    draw = ImageDraw.Draw(img)
    draw.line([(0, line_y), (img.width, line_y)],
              fill=span.color, width=max(2, span.font_size // 20))
    return img


def clear_font_cache() -> None:
    _FONT_CACHE.clear()
