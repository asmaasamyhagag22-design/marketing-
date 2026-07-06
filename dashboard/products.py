"""Pickable PRODUCTS for the studio's product-picker, extracted from the RAW scrape (not the
profile — a brand's `content_images` turned out to be store-location photos, not products).

The owner/engineer want the user to CHOOSE which product/line to advertise, from all the scraped
data, then generate a poster + reel FOR that specific product. This module turns a scrape manifest
into a grounded list of {name, image, url}: the product LINES the crawl actually reached (Shopify
`/collections/<slug>` and `/products/<slug>` pages), each paired with a real product image from the
manifest's images-of-interest. Everything is GROUNDED — a name is a real page the crawl fetched, an
image is a real asset on the site; nothing invented. Empty list when no product page was reached.
"""
from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

# Non-product images to never offer as a product thumbnail (banners, logos, icons, payment badges).
_IMG_SKIP = ("banner", "slide", "logo", "icon", "sprite", "payment", "visa", "mastercard",
             "placeholder", "favicon", "badge")


def _titleize(slug: str) -> str:
    """'shop-hair-care' -> 'Hair Care'; '/collections/b2g1-eid-offer' -> 'B2G1 Eid Offer'."""
    s = re.sub(r"[-_]+", " ", slug).strip()
    s = re.sub(r"\b(shop|collection|collections|all|the)\b", "", s, flags=re.I).strip()
    return " ".join(w.upper() if (w.isupper() or re.fullmatch(r"[a-z]?\d.*", w)) else w.capitalize()
                    for w in s.split()) or slug


def _line_name_from_url(url: str) -> str | None:
    """A product-LINE name from a Shopify-style /collections/<slug> or /products/<slug> URL."""
    path = urlparse(url).path.rstrip("/")
    m = re.search(r"/(?:collections|products|product-category|shop)/([^/]+)$", path)
    return _titleize(m.group(1)) if m else None


def _content_images(manifest: dict) -> list[dict]:
    """Real product-ish images from the manifest's images_of_interest (role=content, not chrome)."""
    out = []
    for im in (manifest.get("images_of_interest") or []):
        if not isinstance(im, dict):
            continue
        if im.get("role") not in (None, "content", "product"):
            continue
        src = str(im.get("src") or "")
        low = (src + " " + str(im.get("alt") or "")).lower()
        if not src.startswith("http") or any(k in low for k in _IMG_SKIP):
            continue
        out.append({"src": src, "alt": str(im.get("alt") or "")})
    return out


def _best_image(name: str, images: list[dict], used: set) -> str:
    """Pick the image whose alt/filename best matches the line name; else the next unused one."""
    words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) >= 3]
    for im in images:
        blob = (im["src"] + " " + im["alt"]).lower()
        if im["src"] not in used and any(w in blob for w in words):
            used.add(im["src"])
            return im["src"]
    for im in images:                       # fall back to any unused real image
        if im["src"] not in used:
            used.add(im["src"])
            return im["src"]
    return images[0]["src"] if images else ""


def products_from_manifest(manifest: dict, *, limit: int = 12) -> list[dict]:
    """Grounded pickable products from one scrape manifest: [{name, image, url}]."""
    images = _content_images(manifest)
    seen: set[str] = set()
    used: set[str] = set()
    out: list[dict] = []
    for page in (manifest.get("pages") or []):
        url = page.get("final_url") or page.get("url") or ""
        name = _line_name_from_url(url)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name, "url": url, "image": _best_image(name, images, used)})
        if len(out) >= limit:
            break
    return out


def _latest_manifest(slug: str, scrapes_dir: str = "scrapes") -> Path | None:
    """The freshest saved scrape manifest for a brand slug (scrapes/<slug>_<ts>/manifest.json)."""
    hits = glob.glob(os.path.join(scrapes_dir, f"{slug}_*", "manifest.json"))
    if not hits:
        return None
    return Path(max(hits, key=os.path.getmtime))


def products_for_slug(slug: str, *, scrapes_dir: str = "scrapes", limit: int = 12) -> list[dict]:
    """Pickable products for a brand slug — reads its freshest manifest. [] if none/unreadable."""
    mp = _latest_manifest(slug, scrapes_dir)
    if not mp:
        return []
    try:
        return products_from_manifest(json.loads(mp.read_text(encoding="utf-8")), limit=limit)
    except Exception:
        return []
