from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw

from poster.schemas import BackgroundImageResult, PosterArtDirection


def _target_size(output_format: str) -> tuple[int, int]:
    if output_format == "a4_print":
        return 2480, 3508
    return 1080, 1350


def _provider_name() -> str:
    return os.getenv("IMAGE_PROVIDER", "openai").strip().lower()


def _openai_model() -> str:
    return os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1").strip()


def _decode_openai_image_response(response: object) -> bytes:
    """
    Supports both:
    - b64_json image responses
    - url image responses
    """
    data = getattr(response, "data", None)
    if not data:
        raise RuntimeError("OpenAI image response did not include data.")

    first = data[0]

    b64_json = getattr(first, "b64_json", None)
    if b64_json:
        return base64.b64decode(b64_json)

    url = getattr(first, "url", None)
    if url:
        request = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (MarketingStrategistPoster/1.0)"},
        )
        with urlopen(request, timeout=30) as r:
            return r.read()

    raise RuntimeError("OpenAI image response had neither b64_json nor url.")


def _save_image_bytes_as_png(
    image_bytes: bytes,
    output_path: Path,
    target_size: tuple[int, int],
) -> tuple[int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    img = Image.open(__import__("io").BytesIO(image_bytes)).convert("RGB")
    img = _cover_resize(img, target_size)
    img.save(output_path, "PNG")

    return img.size


def _cover_resize(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    target_w, target_h = target_size
    src_w, src_h = img.size

    scale = max(target_w / src_w, target_h / src_h)
    new_size = (int(src_w * scale), int(src_h * scale))

    resized = img.resize(new_size, Image.LANCZOS)

    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2

    return resized.crop((left, top, left + target_w, top + target_h))


def _fallback_background(
    art_direction: PosterArtDirection,
    output_path: Path,
    target_size: tuple[int, int],
    reason: str,
) -> BackgroundImageResult:
    """
    Deterministic fallback if OpenAI is unavailable.
    Still better than failing the product demo.
    """
    width, height = target_size
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if art_direction.category == "education":
        top = (6, 18, 35)
        bottom = (18, 68, 102)
        accent = (68, 160, 210)
    elif art_direction.category == "restaurant":
        top = (28, 14, 8)
        bottom = (88, 45, 25)
        accent = (210, 166, 82)
    elif art_direction.category == "medical":
        top = (10, 34, 54)
        bottom = (94, 158, 190)
        accent = (225, 242, 248)
    elif art_direction.category == "skincare":
        top = (72, 47, 58)
        bottom = (220, 185, 166)
        accent = (255, 240, 232)
    else:
        top = (16, 25, 43)
        bottom = (76, 118, 145)
        accent = (220, 190, 120)

    img = Image.new("RGB", (width, height), top)
    draw = ImageDraw.Draw(img)

    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = (
            int(top[0] * (1 - ratio) + bottom[0] * ratio),
            int(top[1] * (1 - ratio) + bottom[1] * ratio),
            int(top[2] * (1 - ratio) + bottom[2] * ratio),
        )
        draw.line((0, y, width, y), fill=color)

    # Soft abstract shapes.
    for i in range(12):
        x = int(width * ((i * 0.173) % 1))
        y = int(height * ((i * 0.231) % 1))
        r = int(width * (0.06 + (i % 3) * 0.025))
        shape_color = (
            min(255, int(accent[0] * 0.75)),
            min(255, int(accent[1] * 0.75)),
            min(255, int(accent[2] * 0.75)),
        )
        draw.ellipse((x - r, y - r, x + r, y + r), outline=shape_color, width=2)

    img.save(output_path, "PNG")

    return BackgroundImageResult(
        provider="fallback",
        model=None,
        prompt=art_direction.provider_prompt,
        background_path=str(output_path),
        filename=output_path.name,
        width=width,
        height=height,
        fallback_used=True,
        fallback_reason=reason,
    )


def generate_background_image(
    art_direction: PosterArtDirection,
    output_dir: str | Path = "outputs/posters/backgrounds",
    output_format: str = "poster_1080x1350",
) -> BackgroundImageResult:
    """
    Generate a background image.

    OpenAI is used only for the visual scene/background.
    Text/logo/CTA are composed later with Pillow.
    """
    output_dir = Path(output_dir)
    target_size = _target_size(output_format)

    filename = f"background_{art_direction.category}_{uuid.uuid4().hex[:8]}.png"
    output_path = output_dir / filename

    provider = _provider_name()

    if provider not in {"openai", "gpt", "gpt-image"}:
        return _fallback_background(
            art_direction,
            output_path,
            target_size,
            reason=f"IMAGE_PROVIDER={provider!r}; OpenAI not selected.",
        )

    if not os.getenv("OPENAI_API_KEY"):
        return _fallback_background(
            art_direction,
            output_path,
            target_size,
            reason="OPENAI_API_KEY is missing.",
        )

    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI()
        model = _openai_model()

        prompt = (
            art_direction.provider_prompt
            + "\n\nNegative constraints:\n"
            + art_direction.negative_prompt
        )

        try:
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size="1024x1536",
                n=1,
            )
        except Exception:
            # Some models/accounts only allow square. Retry safely.
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size="1024x1024",
                n=1,
            )

        image_bytes = _decode_openai_image_response(response)
        width, height = _save_image_bytes_as_png(image_bytes, output_path, target_size)

        return BackgroundImageResult(
            provider="openai",
            model=model,
            prompt=prompt,
            background_path=str(output_path),
            filename=filename,
            width=width,
            height=height,
            fallback_used=False,
            fallback_reason=None,
        )

    except Exception as exc:
        return _fallback_background(
            art_direction,
            output_path,
            target_size,
            reason=f"OpenAI image generation failed: {exc}",
        )