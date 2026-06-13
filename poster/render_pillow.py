from __future__ import annotations

import base64
import io
import re
import uuid
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from poster.schemas import BackgroundImageResult, PosterArtDirection, PosterBrief, PosterRenderResult


# ---------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------

def _mix(
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    ratio: float,
) -> tuple[int, int, int]:
    ratio = max(0.0, min(1.0, ratio))
    return (
        int(a[0] * (1 - ratio) + b[0] * ratio),
        int(a[1] * (1 - ratio) + b[1] * ratio),
        int(a[2] * (1 - ratio) + b[2] * ratio),
    )


def _relative_luminance(color: tuple[int, int, int]) -> float:
    def channel(v: int) -> float:
        x = v / 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = color
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la = _relative_luminance(a)
    lb = _relative_luminance(b)
    lighter = max(la, lb)
    darker = min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _best_text_color(
    background: tuple[int, int, int],
    candidates: list[tuple[int, int, int]],
) -> tuple[int, int, int]:
    fallback_light = (248, 243, 235)
    fallback_dark = (8, 13, 22)
    all_candidates = candidates + [fallback_light, fallback_dark]
    return max(all_candidates, key=lambda c: _contrast_ratio(background, c))


def _safe_filename(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return slug[:60] or "poster"


def _hex_to_rgb(value: str | None, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    if not value:
        return fallback

    try:
        cleaned = value.strip().lstrip("#")
        if len(cleaned) == 3:
            cleaned = "".join(ch * 2 for ch in cleaned)
        if len(cleaned) != 6:
            return fallback
        return tuple(int(cleaned[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except Exception:
        return fallback


def _brand_accent(brief: PosterBrief) -> tuple[int, int, int]:
    palette = brief.palette_hex or []
    candidates = [brief.primary_color, *palette]

    for item in candidates:
        color = _hex_to_rgb(item, (255, 255, 255))
        if color != (255, 255, 255):
            return color

    return (80, 160, 220)


# ---------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------

def _font(
    size: int,
    *,
    bold: bool = False,
    italic: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates: list[str] = []

    if bold:
        candidates += [
            "C:/Windows/Fonts/georgiab.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    elif italic:
        candidates += [
            "C:/Windows/Fonts/georgiai.ttf",
            "C:/Windows/Fonts/ariali.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        ]
    else:
        candidates += [
            "C:/Windows/Fonts/georgia.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)

    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = str(text).split()
    if not words:
        return []

    lines: list[str] = []
    current: list[str] = []

    for word in words:
        trial = " ".join(current + [word])
        width, _ = _text_size(draw, trial, font)

        if width <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]

    if current:
        lines.append(" ".join(current))

    return lines


def _draw_shadowed_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    shadow_alpha: int = 150,
) -> None:
    x, y = xy
    shadow = (0, 0, 0, shadow_alpha)

    for dx, dy in [(2, 2), (0, 2), (2, 0)]:
        draw.text((x + dx, y + dy), text, font=font, fill=shadow)

    draw.text((x, y), text, font=font, fill=fill)


def _draw_centered_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    width: int,
    max_width: int,
    line_gap: int,
    max_lines: Optional[int] = None,
) -> int:
    lines = _wrap_text(draw, text, font, max_width)
    if max_lines is not None:
        lines = lines[:max_lines]

    for line in lines:
        tw, th = _text_size(draw, line, font)
        _draw_shadowed_text(draw, ((width - tw) // 2, y), line, font, fill)
        y += th + line_gap

    return y


def _draw_left_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
    line_gap: int,
    max_lines: Optional[int] = None,
) -> int:
    lines = _wrap_text(draw, text, font, max_width)
    if max_lines is not None:
        lines = lines[:max_lines]

    for line in lines:
        _, th = _text_size(draw, line, font)
        _draw_shadowed_text(draw, (x, y), line, font, fill)
        y += th + line_gap

    return y


def _format_url(url: Optional[str]) -> str:
    if not url:
        return ""

    return url.replace("https://", "").replace("http://", "").rstrip("/")


# ---------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------

def _cover_resize(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    target_w, target_h = target_size
    src_w, src_h = img.size

    scale = max(target_w / src_w, target_h / src_h)
    new_size = (int(src_w * scale), int(src_h * scale))

    resized = img.resize(new_size, Image.LANCZOS)

    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2

    return resized.crop((left, top, left + target_w, top + target_h))


def _load_background(background: BackgroundImageResult, size: tuple[int, int]) -> Image.Image:
    path = Path(background.background_path)

    if path.exists():
        img = Image.open(path).convert("RGB")
        return _cover_resize(img, size).convert("RGBA")

    img = Image.new("RGB", size, (18, 24, 32))
    return img.convert("RGBA")


def _load_remote_image(url: str, timeout: int = 8) -> Optional[Image.Image]:
    try:
        request = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (MarketingStrategistPoster/1.0)"},
        )

        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            data = response.read(3_000_000)

        if "svg" in content_type or url.lower().endswith(".svg"):
            return None

        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
        return image.convert("RGBA")

    except (OSError, UnidentifiedImageError, TimeoutError, ValueError):
        return None
    except Exception:
        return None


def _fit_image_contain(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    img = image.copy()
    img.thumbnail((max_width, max_height), Image.LANCZOS)
    return img


def _apply_full_bleed_scrim(img: Image.Image, strength: int = 110) -> None:
    width, height = img.size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for y in range(height):
        top_ratio = max(0.0, 1.0 - y / (height * 0.45))
        bottom_ratio = max(0.0, (y - height * 0.58) / (height * 0.42))
        alpha = int(55 + strength * max(top_ratio, bottom_ratio))
        alpha = max(50, min(185, alpha))
        draw.line((0, y, width, y), fill=(0, 0, 0, alpha))

    img.alpha_composite(overlay)


def _draw_soft_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    alpha: int = 150,
) -> None:
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=(5, 12, 22, alpha),
        outline=(255, 255, 255, 160),
        width=2,
    )


def _draw_logo(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    brief: PosterBrief,
    box: tuple[int, int, int, int],
    scale: float,
    light_plate: bool = True,
) -> None:
    x1, y1, x2, y2 = box

    if light_plate:
        plate_fill = (255, 255, 255, 232)
        plate_text = (12, 24, 40)
        outline = (255, 255, 255, 210)
    else:
        plate_fill = (7, 13, 24, 188)
        plate_text = (245, 248, 255)
        outline = (255, 255, 255, 160)

    draw.rounded_rectangle(
        box,
        radius=int(24 * scale),
        fill=plate_fill,
        outline=outline,
        width=max(1, int(2 * scale)),
    )

    logo_img = _load_remote_image(brief.logo_url) if brief.logo_url else None

    if logo_img is not None:
        max_w = x2 - x1 - int(46 * scale)
        max_h = y2 - y1 - int(26 * scale)
        fitted = _fit_image_contain(logo_img, max_w, max_h)

        px = x1 + ((x2 - x1) - fitted.width) // 2
        py = y1 + ((y2 - y1) - fitted.height) // 2

        base.alpha_composite(fitted, (px, py))
        return

    wordmark = brief.logo_text or brief.business_name
    font_size = int(36 * scale)
    wordmark_font = _font(font_size, bold=True)

    while True:
        tw, th = _text_size(draw, wordmark.upper(), wordmark_font)
        if tw <= (x2 - x1 - int(50 * scale)) or font_size <= int(23 * scale):
            break
        font_size -= int(2 * scale)
        wordmark_font = _font(font_size, bold=True)

    tw, th = _text_size(draw, wordmark.upper(), wordmark_font)
    draw.text(
        (x1 + ((x2 - x1) - tw) // 2, y1 + ((y2 - y1) - th) // 2),
        wordmark.upper(),
        font=wordmark_font,
        fill=plate_text,
    )


def _draw_chips(
    draw: ImageDraw.ImageDraw,
    items: list[str],
    y: int,
    width: int,
    scale: float,
    accent: tuple[int, int, int],
    centered: bool = True,
    x_start: Optional[int] = None,
    max_width: Optional[int] = None,
) -> int:
    font = _font(int(18 * scale), bold=True)
    chips = [item.upper() for item in items[:3] if item]

    if not chips:
        return y

    chip_specs: list[tuple[str, int, int]] = []
    for chip in chips:
        tw, th = _text_size(draw, chip, font)
        chip_specs.append((chip, tw + int(34 * scale), th + int(18 * scale)))

    available = max_width or (width - int(120 * scale))
    total_w = sum(w for _, w, _ in chip_specs) + int(12 * scale) * (len(chip_specs) - 1)

    if total_w <= available:
        x = ((width - total_w) // 2) if centered else (x_start or int(70 * scale))
        for chip, chip_w, chip_h in chip_specs:
            draw.rounded_rectangle(
                (x, y, x + chip_w, y + chip_h),
                radius=int(20 * scale),
                fill=(255, 255, 255, 34),
                outline=(*accent, 210),
                width=1,
            )
            tw, th = _text_size(draw, chip, font)
            _draw_shadowed_text(
                draw,
                (x + (chip_w - tw) // 2, y + (chip_h - th) // 2),
                chip,
                font,
                (245, 248, 255),
            )
            x += chip_w + int(12 * scale)

        return y + max(h for _, _, h in chip_specs)

    # Fallback: vertical chips
    x = x_start or int(90 * scale)
    chip_max_w = available
    current_y = y

    for chip in chips:
        lines = _wrap_text(draw, chip, font, chip_max_w - int(38 * scale))[:2]
        chip_h = int(28 * scale) + len(lines) * int(23 * scale)

        draw.rounded_rectangle(
            (x, current_y, x + chip_max_w, current_y + chip_h),
            radius=int(20 * scale),
            fill=(255, 255, 255, 34),
            outline=(*accent, 210),
            width=1,
        )

        ly = current_y + int(13 * scale)
        for line in lines:
            _draw_shadowed_text(
                draw,
                (x + int(18 * scale), ly),
                line,
                font,
                (245, 248, 255),
            )
            ly += int(23 * scale)

        current_y += chip_h + int(10 * scale)

    return current_y


def _draw_cta(
    draw: ImageDraw.ImageDraw,
    brief: PosterBrief,
    box: tuple[int, int, int, int],
    scale: float,
    light: bool = True,
) -> None:
    x1, y1, x2, y2 = box

    if light:
        fill = (255, 255, 255, 232)
        text = (8, 18, 32)
        outline = (255, 255, 255, 230)
    else:
        fill = (5, 12, 22, 210)
        text = (245, 248, 255)
        outline = (255, 255, 255, 175)

    draw.rounded_rectangle(
        box,
        radius=int(24 * scale),
        fill=fill,
        outline=outline,
        width=max(1, int(2 * scale)),
    )

    cta_font = _font(int(27 * scale), bold=True)
    url_font = _font(int(33 * scale), bold=True)

    cta = brief.cta_text.upper()
    cw, _ = _text_size(draw, cta, cta_font)
    draw.text(((x1 + x2 - cw) // 2, y1 + int(19 * scale)), cta, font=cta_font, fill=text)

    url = _format_url(brief.cta_url).upper()
    if url:
        if len(url) > 36:
            url_font = _font(int(24 * scale), bold=True)

        uw, _ = _text_size(draw, url, url_font)
        draw.text(((x1 + x2 - uw) // 2, y1 + int(60 * scale)), url, font=url_font, fill=text)


def _draw_contact(
    draw: ImageDraw.ImageDraw,
    brief: PosterBrief,
    width: int,
    y: int,
    scale: float,
) -> None:
    if not brief.contact_line:
        return

    font = _font(int(20 * scale))
    tw, _ = _text_size(draw, brief.contact_line, font)
    _draw_shadowed_text(
        draw,
        ((width - tw) // 2, y),
        brief.contact_line,
        font,
        (245, 248, 255),
    )


# ---------------------------------------------------------------------
# Layouts
# ---------------------------------------------------------------------

def _layout_magazine_cover(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    brief: PosterBrief,
    art: PosterArtDirection,
    width: int,
    height: int,
    scale: float,
    accent: tuple[int, int, int],
) -> None:
    _apply_full_bleed_scrim(img, strength=130)

    margin = int(42 * scale)
    draw.rounded_rectangle(
        (margin, margin, width - margin, height - margin),
        radius=int(34 * scale),
        outline=(255, 255, 255, 190),
        width=max(2, int(3 * scale)),
    )

    _draw_logo(
        img,
        draw,
        brief,
        (
            int(72 * scale),
            int(70 * scale),
            int(305 * scale),
            int(142 * scale),
        ),
        scale,
        light_plate=True,
    )

    y = int(235 * scale)

    category_font = _font(int(18 * scale), bold=True)
    category = (brief.category or "brand").replace("_", " ").upper()
    cw, _ = _text_size(draw, category, category_font)
    _draw_shadowed_text(draw, ((width - cw) // 2, y), category, category_font, accent)
    y += int(46 * scale)

    title_font = _font(int(72 * scale), bold=True)
    y = _draw_centered_wrapped(
        draw,
        brief.business_name.upper(),
        y,
        title_font,
        (248, 243, 235),
        width,
        width - int(135 * scale),
        int(6 * scale),
        max_lines=2,
    )

    y += int(22 * scale)

    headline_font = _font(int(33 * scale), italic=True)
    y = _draw_centered_wrapped(
        draw,
        brief.headline,
        y,
        headline_font,
        (232, 240, 250),
        width,
        width - int(185 * scale),
        int(7 * scale),
        max_lines=2,
    )

    y += int(36 * scale)

    hook_font = _font(int(37 * scale), bold=True)
    _draw_centered_wrapped(
        draw,
        art.safe_overlay_copy.upper(),
        y,
        hook_font,
        (255, 255, 255),
        width,
        width - int(170 * scale),
        int(7 * scale),
        max_lines=2,
    )

    chips_y = int(790 * scale)
    _draw_chips(draw, brief.offerings, chips_y, width, scale, accent)

    _draw_cta(
        draw,
        brief,
        (
            int(128 * scale),
            int(1040 * scale),
            width - int(128 * scale),
            int(1162 * scale),
        ),
        scale,
        light=True,
    )

    _draw_contact(draw, brief, width, int(1232 * scale), scale)


def _layout_split_editorial(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    brief: PosterBrief,
    art: PosterArtDirection,
    width: int,
    height: int,
    scale: float,
    accent: tuple[int, int, int],
) -> None:
    _apply_full_bleed_scrim(img, strength=90)

    panel = (
        int(56 * scale),
        int(66 * scale),
        int(535 * scale),
        height - int(72 * scale),
    )

    _draw_soft_panel(draw, panel, int(34 * scale), alpha=188)

    _draw_logo(
        img,
        draw,
        brief,
        (
            panel[0] + int(36 * scale),
            panel[1] + int(36 * scale),
            panel[0] + int(290 * scale),
            panel[1] + int(108 * scale),
        ),
        scale,
        light_plate=True,
    )

    x = panel[0] + int(38 * scale)
    y = panel[1] + int(150 * scale)

    category_font = _font(int(17 * scale), bold=True)
    category = (brief.category or "brand").replace("_", " ").upper()
    _draw_shadowed_text(draw, (x, y), category, category_font, accent)
    y += int(52 * scale)

    title_font = _font(int(54 * scale), bold=True)
    y = _draw_left_wrapped(
        draw,
        brief.business_name.upper(),
        x,
        y,
        title_font,
        (248, 243, 235),
        panel[2] - x - int(32 * scale),
        int(5 * scale),
        max_lines=3,
    )

    y += int(28 * scale)

    headline_font = _font(int(29 * scale), italic=True)
    y = _draw_left_wrapped(
        draw,
        brief.headline,
        x,
        y,
        headline_font,
        (230, 238, 248),
        panel[2] - x - int(32 * scale),
        int(7 * scale),
        max_lines=3,
    )

    if brief.subheadline:
        y += int(24 * scale)
        body_font = _font(int(21 * scale))
        y = _draw_left_wrapped(
            draw,
            brief.subheadline,
            x,
            y,
            body_font,
            (235, 241, 248),
            panel[2] - x - int(32 * scale),
            int(7 * scale),
            max_lines=5,
        )

    y += int(30 * scale)

    _draw_chips(
        draw,
        brief.offerings,
        y,
        width,
        scale,
        accent,
        centered=False,
        x_start=x,
        max_width=panel[2] - x - int(38 * scale),
    )

    _draw_cta(
        draw,
        brief,
        (
            x,
            height - int(250 * scale),
            panel[2] - int(38 * scale),
            height - int(130 * scale),
        ),
        scale,
        light=True,
    )

    _draw_contact(draw, brief, width, height - int(55 * scale), scale)


def _layout_bottom_band(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    brief: PosterBrief,
    art: PosterArtDirection,
    width: int,
    height: int,
    scale: float,
    accent: tuple[int, int, int],
) -> None:
    _apply_full_bleed_scrim(img, strength=95)

    _draw_logo(
        img,
        draw,
        brief,
        (
            int(70 * scale),
            int(70 * scale),
            int(335 * scale),
            int(146 * scale),
        ),
        scale,
        light_plate=True,
    )

    title_font = _font(int(68 * scale), bold=True)
    y = int(230 * scale)

    y = _draw_centered_wrapped(
        draw,
        brief.business_name.upper(),
        y,
        title_font,
        (248, 243, 235),
        width,
        width - int(150 * scale),
        int(6 * scale),
        max_lines=2,
    )

    band = (
        int(58 * scale),
        int(765 * scale),
        width - int(58 * scale),
        height - int(74 * scale),
    )

    _draw_soft_panel(draw, band, int(34 * scale), alpha=202)

    y = band[1] + int(42 * scale)

    headline_font = _font(int(38 * scale), bold=True)
    y = _draw_centered_wrapped(
        draw,
        art.safe_overlay_copy.upper(),
        y,
        headline_font,
        (255, 255, 255),
        width,
        band[2] - band[0] - int(80 * scale),
        int(8 * scale),
        max_lines=2,
    )

    if brief.subheadline:
        y += int(12 * scale)
        body_font = _font(int(22 * scale))
        y = _draw_centered_wrapped(
            draw,
            brief.subheadline,
            y,
            body_font,
            (230, 238, 248),
            width,
            band[2] - band[0] - int(105 * scale),
            int(6 * scale),
            max_lines=3,
        )

    y += int(30 * scale)
    y = _draw_chips(draw, brief.offerings, y, width, scale, accent)

    y += int(30 * scale)

    _draw_cta(
        draw,
        brief,
        (
            int(128 * scale),
            y,
            width - int(128 * scale),
            y + int(118 * scale),
        ),
        scale,
        light=True,
    )

    _draw_contact(draw, brief, width, height - int(55 * scale), scale)


def _layout_clean_institutional(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    brief: PosterBrief,
    art: PosterArtDirection,
    width: int,
    height: int,
    scale: float,
    accent: tuple[int, int, int],
) -> None:
    _apply_full_bleed_scrim(img, strength=105)

    # Elegant diagonal brand accent.
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.polygon(
        [
            (0, int(0.74 * height)),
            (width, int(0.58 * height)),
            (width, height),
            (0, height),
        ],
        fill=(5, 12, 22, 205),
    )
    img.alpha_composite(overlay)

    margin = int(42 * scale)
    draw.rounded_rectangle(
        (margin, margin, width - margin, height - margin),
        radius=int(30 * scale),
        outline=(255, 255, 255, 180),
        width=max(2, int(3 * scale)),
    )

    _draw_logo(
        img,
        draw,
        brief,
        (
            int(360 * scale),
            int(72 * scale),
            width - int(360 * scale),
            int(150 * scale),
        ),
        scale,
        light_plate=True,
    )

    y = int(220 * scale)

    category_font = _font(int(17 * scale), bold=True)
    category = (brief.category or "brand").replace("_", " ").upper()
    cw, _ = _text_size(draw, category, category_font)
    _draw_shadowed_text(draw, ((width - cw) // 2, y), category, category_font, accent)
    y += int(44 * scale)

    title_font = _font(int(64 * scale), bold=True)
    y = _draw_centered_wrapped(
        draw,
        brief.business_name.upper(),
        y,
        title_font,
        (248, 243, 235),
        width,
        width - int(145 * scale),
        int(6 * scale),
        max_lines=2,
    )

    y += int(20 * scale)

    headline_font = _font(int(34 * scale), italic=True)
    y = _draw_centered_wrapped(
        draw,
        brief.headline,
        y,
        headline_font,
        (232, 240, 250),
        width,
        width - int(170 * scale),
        int(8 * scale),
        max_lines=2,
    )

    main_panel = (
        int(92 * scale),
        int(680 * scale),
        width - int(92 * scale),
        int(910 * scale),
    )

    _draw_soft_panel(draw, main_panel, int(30 * scale), alpha=170)

    hook_font = _font(int(37 * scale), bold=True)
    y = main_panel[1] + int(44 * scale)

    y = _draw_centered_wrapped(
        draw,
        art.safe_overlay_copy.upper(),
        y,
        hook_font,
        (255, 255, 255),
        width,
        main_panel[2] - main_panel[0] - int(88 * scale),
        int(8 * scale),
        max_lines=2,
    )

    if brief.subheadline:
        body_font = _font(int(21 * scale))
        y += int(10 * scale)
        _draw_centered_wrapped(
            draw,
            brief.subheadline,
            y,
            body_font,
            (230, 238, 248),
            width,
            main_panel[2] - main_panel[0] - int(100 * scale),
            int(6 * scale),
            max_lines=2,
        )

    chips_y = int(970 * scale)
    _draw_chips(draw, brief.offerings, chips_y, width, scale, accent)

    _draw_cta(
        draw,
        brief,
        (
            int(128 * scale),
            int(1110 * scale),
            width - int(128 * scale),
            int(1228 * scale),
        ),
        scale,
        light=True,
    )

    _draw_contact(draw, brief, width, height - int(55 * scale), scale)


def _layout_hero_overlay(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    brief: PosterBrief,
    art: PosterArtDirection,
    width: int,
    height: int,
    scale: float,
    accent: tuple[int, int, int],
) -> None:
    # For now, hero_overlay is a cleaner magazine-like layout.
    _layout_magazine_cover(img, draw, brief, art, width, height, scale, accent)


# ---------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------

def render_poster(
    brief: PosterBrief,
    art_direction: PosterArtDirection,
    background: BackgroundImageResult,
    output_dir: str | Path = "outputs/posters",
    output_format: str = "poster_1080x1350",
) -> tuple[PosterRenderResult, str]:
    if output_format == "a4_print":
        width, height = 2480, 3508
    else:
        width, height = 1080, 1350

    scale = width / 1080
    accent = _brand_accent(brief)

    img = _load_background(background, (width, height))
    draw = ImageDraw.Draw(img, "RGBA")

    layout = art_direction.layout

    if layout == "split_editorial":
        _layout_split_editorial(img, draw, brief, art_direction, width, height, scale, accent)
    elif layout == "bottom_band":
        _layout_bottom_band(img, draw, brief, art_direction, width, height, scale, accent)
    elif layout == "clean_institutional":
        _layout_clean_institutional(img, draw, brief, art_direction, width, height, scale, accent)
    elif layout == "hero_overlay":
        _layout_hero_overlay(img, draw, brief, art_direction, width, height, scale, accent)
    else:
        _layout_magazine_cover(img, draw, brief, art_direction, width, height, scale, accent)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    filename = f"{_safe_filename(brief.business_name)}_poster_{uuid.uuid4().hex[:8]}.png"
    file_path = output_path / filename

    rgb_img = img.convert("RGB")

    save_kwargs = {}
    if output_format == "a4_print":
        save_kwargs["dpi"] = (300, 300)

    rgb_img.save(file_path, "PNG", **save_kwargs)

    image_base64 = base64.b64encode(file_path.read_bytes()).decode("utf-8")

    result = PosterRenderResult(
        poster_path=str(file_path),
        filename=filename,
        width=width,
        height=height,
    )

    return result, image_base64