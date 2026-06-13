"""Images of interest.

For v0.1 we only record three high-confidence roles:
- LOGO: <img> inside <header>, or alt containing 'logo'
- HERO: the first large above-fold <img> not classified as logo
- OG_IMAGE: from <meta property="og:image">

This keeps the manifest small and avoids classifying gallery /
product images we can't role-tag reliably.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..schemas import ImageOfInterest, ImageRole


def _as_int(x) -> Optional[int]:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def extract_images_of_interest(
    html: str,
    page_url: str,
    og_image_url: Optional[str] = None,
    viewport_height: int = 800,
) -> list[ImageOfInterest]:
    out: list[ImageOfInterest] = []
    seen_srcs: set[str] = set()

    if not html:
        if og_image_url and og_image_url not in seen_srcs:
            out.append(ImageOfInterest(
                role=ImageRole.OG_IMAGE, src=og_image_url, page_url=page_url
            ))
        return out

    soup = BeautifulSoup(html, "lxml")

    # ----- Logo: first <img> inside <header>, else alt-contains-'logo' -----
    logo_el = None
    header = soup.find("header")
    if header:
        logo_el = header.find("img")
    if logo_el is None:
        for img in soup.find_all("img"):
            alt = (img.get("alt") or "").lower()
            if "logo" in alt:
                logo_el = img
                break

    if logo_el is not None and logo_el.get("src"):
        src = urljoin(page_url, logo_el["src"])
        seen_srcs.add(src)
        out.append(ImageOfInterest(
            role=ImageRole.LOGO,
            src=src,
            alt=logo_el.get("alt"),
            page_url=page_url,
            width=_as_int(logo_el.get("width")),
            height=_as_int(logo_el.get("height")),
            above_fold=True,  # logos are essentially always above the fold
        ))

    # ----- Hero: first large <img> in <main>/<body>, skipping logo -----
    candidates = soup.select("main img, section img, body img")
    hero_el = None
    for img in candidates:
        if logo_el is not None and img is logo_el:
            continue
        if not img.get("src"):
            continue
        w = _as_int(img.get("width"))
        h = _as_int(img.get("height"))
        # Prefer images explicitly sized large, or with no size info
        if w is None or w >= 300:
            hero_el = img
            break
    if hero_el is not None:
        src = urljoin(page_url, hero_el["src"])
        if src not in seen_srcs:
            seen_srcs.add(src)
            out.append(ImageOfInterest(
                role=ImageRole.HERO,
                src=src,
                alt=hero_el.get("alt"),
                page_url=page_url,
                width=_as_int(hero_el.get("width")),
                height=_as_int(hero_el.get("height")),
                above_fold=True,
            ))

    # ----- OG image (from metadata) -----
    if og_image_url:
        og_abs = urljoin(page_url, og_image_url)
        if og_abs not in seen_srcs:
            seen_srcs.add(og_abs)
            out.append(ImageOfInterest(
                role=ImageRole.OG_IMAGE,
                src=og_abs,
                page_url=page_url,
            ))

    return out
