"""Vision-based selection of the brand's REAL photos for the reel.

The scraper collects every on-page image; many are NOT footage you'd put in a
marketing reel — partner/sponsor logos (Microsoft, AWS, ...), QR codes, icons,
diagrams, text banners, screenshots. Animating those is the "زوّم على QR code"
bug. URL/extension heuristics can't tell a partner logo from a real photo, so we
SHOW each image to a vision model together with the business identity and keep
only real, on-brand PHOTOGRAPHS of THIS business (its space, people, work, food,
products). Honest-degrade: if no key/SDK/network, return the input unchanged.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Kinds the model assigns. Only REAL_PHOTO is kept for the reel.
_KEEP_KIND = "real_photo"


class PhotoVerdict(BaseModel):
    index: int
    kind: str = Field(description=(
        "one of: real_photo (a genuine photograph of THIS business — its space, "
        "people, staff, customers, food, products, work, events), logo, "
        "partner_or_sponsor_logo, qr_code, icon, diagram_or_chart, "
        "text_banner_or_poster, screenshot, stock_or_irrelevant"
    ))
    subject: str = Field(description="3-8 words: what the photo actually shows")
    on_brand: bool = Field(description="true only if it authentically represents THIS business/vertical")
    quality: int = Field(description="1-5: how good a marketing-reel shot it is (5=hero)")


class PhotoSelection(BaseModel):
    verdicts: list[PhotoVerdict]


def _image_data_url(url: str, *, max_side: int = 640) -> Optional[str]:
    """Download an image OURSELVES (cert-tolerant, SSRF-guarded) and return a small
    base64 JPEG data URL. We send bytes, not the URL, so a site that blocks the
    model's image fetcher (e.g. gov.eg) still gets analyzed. None on any failure."""
    import base64
    import io
    from reel.video_provider import _load_reference_image
    loaded = _load_reference_image(url)
    if not loaded:
        return None
    data, _mime = loaded
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        data = buf.getvalue()
    except Exception:
        pass  # PIL missing/odd format -> send original bytes
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def _system_prompt(business_name: str, category: str, description: str) -> str:
    return (
        "You are a senior video art director selecting shots for a vertical marketing "
        f"REEL for this specific business:\n"
        f"  Name: {business_name}\n  Category/field: {category or 'unknown'}\n"
        f"  About: {description or '(no description)'}\n\n"
        "You are shown numbered images scraped from the business's own website. For EACH "
        "image decide what it IS and whether it belongs in the reel. KEEP only kind="
        "'real_photo' that is genuinely a photograph OF THIS business and on-brand for its "
        "field. DROP logos, partner/sponsor badges, QR codes, icons, diagrams/charts, text "
        "banners/posters, screenshots, and generic stock or unrelated images. Be strict: a "
        "company logo (even a partner's) is NOT a real_photo; a QR code is NOT a real_photo. "
        "Return exactly one verdict per image, using its index."
    )


def select_brand_photos(
    image_urls: list[str],
    *,
    business_name: str,
    category: str = "",
    description: str = "",
    max_keep: int = 12,
    model: str = "gpt-4o-mini",
    api_key: Optional[str] = None,
    timeout_s: float = 90.0,
) -> list[str]:
    """Return the subset of `image_urls` that are real, on-brand photographs,
    ordered best-first. Falls back to the input list on any failure (never raises)."""
    # Drop tracking-beacon / non-image hosts up front (defense-in-depth; they also
    # 400 the vision fetch). The scraper excludes these too — belt and suspenders.
    _bad_hosts = ("facebook.com/tr", "/tr?", "google-analytics", "googletagmanager",
                  "doubleclick", "/pixel", "analytics.")
    urls = [u for u in (image_urls or [])
            if isinstance(u, str) and u.startswith(("http://", "https://"))
            and not any(b in u.lower() for b in _bad_hosts)]
    if len(urls) <= 1:
        return urls
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        logger.info("image_select: no OPENAI_API_KEY; keeping all %d images", len(urls))
        return urls[:max_keep]

    # Download + downscale each image OURSELVES; keep only the ones we could fetch
    # (a site that blocks the model's fetcher still works because we send bytes).
    fetched: list[str] = []          # urls we have data for, in order
    data_urls: list[str] = []
    for u in urls:
        d = _image_data_url(u)
        if d:
            fetched.append(u)
            data_urls.append(d)
    if len(fetched) <= 1:
        logger.info("image_select: only %d images fetchable; keeping them", len(fetched))
        return fetched or urls[:max_keep]

    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, timeout=timeout_s)

        content: list[dict] = [{"type": "text", "text": (
            "Classify every image below. Reply with one verdict per image (by index)."
        )}]
        for i, d in enumerate(data_urls):
            content.append({"type": "text", "text": f"Image index {i}:"})
            content.append({"type": "image_url", "image_url": {"url": d, "detail": "low"}})

        completion = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": _system_prompt(business_name, category, description)},
                {"role": "user", "content": content},
            ],
            response_format=PhotoSelection,
            temperature=0.0,
        )
        parsed = completion.choices[0].message.parsed
        urls = fetched                  # indices below refer to the fetched list
        if parsed is None:
            return urls[:max_keep]

        kept: list[tuple[int, str]] = []   # (quality, url)
        dropped: list[str] = []
        for v in parsed.verdicts:
            if not (0 <= v.index < len(urls)):
                continue
            if v.kind == _KEEP_KIND and v.on_brand:
                kept.append((v.quality, urls[v.index]))
            else:
                dropped.append(f"{v.kind}:{v.subject}")
        kept.sort(key=lambda kv: -kv[0])
        result = [u for _, u in kept][:max_keep]
        logger.info("image_select: kept %d/%d (dropped: %s)",
                    len(result), len(urls), "; ".join(dropped[:8]))
        # If the model rejected everything (over-strict / all-logos site), don't
        # leave the reel with zero photos — that's the caller's honest "logo-only"
        # signal, so return empty and let the caller decide.
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("image_select failed (%s); keeping all images", e)
        return urls[:max_keep]
