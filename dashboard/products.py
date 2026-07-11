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
from datetime import datetime, timezone
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


# Offering-type pages whose LEAF entries are pickable products (FIX-A: universal, not Shopify-only)
_OFFERING_PAGE_TYPES = {"products", "courses", "services", "menu", "programs", "pricing"}


def _first_heading(page: dict) -> str:
    """The page's own display name: its first h1/h2 text block (a course page's title), trimmed."""
    for b in (page.get("text_blocks") or []):
        if isinstance(b, dict) and str(b.get("tag") or "").lower() in ("h1", "h2"):
            t = str(b.get("text") or "").strip()
            if 2 <= len(t) <= 90:
                return t
    return ""


def _offering_products(profile: dict | None, images: list[dict], used: set, seen: set,
                       limit: int) -> list[dict]:
    """Pickable products from the PROFILE's extracted offerings — the best-named source (real
    item names + prices, any vertical), which the picker used to ignore entirely."""
    out: list[dict] = []
    for o in ((profile or {}).get("offerings") or []):
        if not isinstance(o, dict):
            continue
        name = o.get("name")
        if isinstance(name, dict):
            name = name.get("value")
        name = str(name or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        price = o.get("price_text")
        out.append({"name": name[:90], "url": str(o.get("page_url") or ""),
                    "image": _best_image(name, images, used),
                    "price_text": price if isinstance(price, str) and price.strip() else None})
        if len(out) >= limit:
            break
    return out


def products_from_manifest(manifest: dict, *, limit: int = 12,
                           profile: dict | None = None) -> list[dict]:
    """Grounded pickable products: [{name, image, url, price_text?}]. Sources in priority order
    (FIX-A — the old picker understood ONLY Shopify URL slugs and returned [] for education/
    services/clinics, verified on nti):
      1. the profile's extracted offerings (real names + prices, every vertical);
      2. manifest pages of an offering type that are LEAF items, named by their own h1/h2;
      3. the Shopify-style URL-slug rule (existing behavior, kept as the fallback)."""
    images = _content_images(manifest)
    seen: set[str] = set()
    used: set[str] = set()
    out: list[dict] = _offering_products(profile, images, used, seen, limit)

    if len(out) < limit:
        try:
            from scraper.classify.page_type import is_leaf_detail  # lazy: no heavy deps
        except Exception:  # noqa: BLE001
            def is_leaf_detail(_u: str) -> bool:
                return False
        for page in (manifest.get("pages") or []):
            if len(out) >= limit:
                break
            url = page.get("final_url") or page.get("url") or ""
            if str(page.get("page_type") or "") not in _OFFERING_PAGE_TYPES or not is_leaf_detail(url):
                continue
            name = _first_heading(page) or _line_name_from_url(url) or ""
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append({"name": name, "url": url, "image": _best_image(name, images, used)})

    for page in (manifest.get("pages") or []):
        if len(out) >= limit:
            break
        url = page.get("final_url") or page.get("url") or ""
        name = _line_name_from_url(url)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name, "url": url, "image": _best_image(name, images, used)})
    return out


def _latest_manifest(slug: str, scrapes_dir: str = "scrapes") -> Path | None:
    """The freshest saved scrape manifest for a brand slug (scrapes/<slug>_<ts>/manifest.json)."""
    hits = glob.glob(os.path.join(scrapes_dir, f"{slug}_*", "manifest.json"))
    if not hits:
        return None
    return Path(max(hits, key=os.path.getmtime))


def _profile_for_slug(slug: str, scrapes_dir: str, out_dir: str) -> dict | None:
    """The freshest extracted profile for a brand: the studio's outputs/<slug>_profile.json,
    else the scrape-dir sibling business_profile.json. None when neither exists."""
    candidates = [Path(out_dir) / f"{slug}_profile.json"]
    mp = _latest_manifest(slug, scrapes_dir)
    if mp:
        candidates.append(mp.parent / "business_profile.json")
    for p in candidates:
        try:
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data.get("profile") if isinstance(data.get("profile"), dict) else data
        except Exception:  # noqa: BLE001
            continue
    return None


def products_for_slug(slug: str, *, scrapes_dir: str = "scrapes", limit: int = 12,
                      out_dir: str = "outputs") -> list[dict]:
    """Pickable products for a brand slug — freshest manifest + extracted profile offerings.
    [] if no scrape exists/unreadable."""
    mp = _latest_manifest(slug, scrapes_dir)
    if not mp:
        return []
    try:
        return products_from_manifest(json.loads(mp.read_text(encoding="utf-8")), limit=limit,
                                      profile=_profile_for_slug(slug, scrapes_dir, out_dir))
    except Exception:
        return []


def _name_words(name: str) -> list[str]:
    """The product name's significant words (>=3 chars), lowercase — the matching key everywhere."""
    return [w for w in re.findall(r"[\w؀-ۿ]+", (name or "").lower()) if len(w) >= 3]


def save_product_scrape(slug: str, product_name: str, *, product_image: str | None = None,
                        kind: str = "", scrapes_dir: str = "scrapes",
                        out_asset: str = "") -> Path | None:
    """OWNER FEATURE: the moment a product-specific ad is generated, persist a PRODUCT-ONLY scrape
    snapshot into the brand's scrape dir — `product_scrape_<product>.json` — so the owner can open
    the scrapes folder and see exactly how far the crawl reached for THAT product: which pages
    matched it, which images, which priced offerings, how many text blocks mention it. Everything
    is read from the existing manifest + profile (grounded, nothing invented). Never raises; None
    when the brand has no saved scrape."""
    mp = _latest_manifest(slug, scrapes_dir)
    if not mp:
        return None
    try:
        m = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:
        return None
    words = _name_words(product_name)

    # pages the crawl fetched that MATCH the product (url or any text block mentions it)
    pages_matched, mention_blocks = [], 0
    for p in (m.get("pages") or []):
        if not isinstance(p, dict):
            continue
        url = str(p.get("final_url") or p.get("url") or "")
        blocks = [str(b.get("text") or "") if isinstance(b, dict) else str(b)
                  for b in (p.get("text_blocks") or [])]
        hits = sum(1 for t in blocks if any(w in t.lower() for w in words))
        mention_blocks += hits
        url_match = any(w in url.lower() for w in words)
        if url_match or hits:
            pages_matched.append({"url": url, "url_match": url_match,
                                  "blocks_mentioning_product": hits, "total_blocks": len(blocks)})

    images_matched = [im for im in _content_images(m)
                      if any(w in (im["src"] + " " + im["alt"]).lower() for w in words)]

    # priced offerings from the profile that match the product name
    offerings_matched = []
    prof_path = mp.parent / "business_profile.json"
    if prof_path.is_file():
        try:
            prof = json.loads(prof_path.read_text(encoding="utf-8"))
            for o in (prof.get("offerings") or []):
                nm = str((o.get("name") if isinstance(o, dict) else "") or "")
                if any(w in nm.lower() for w in words):
                    offerings_matched.append({"name": nm,
                                              "price_text": o.get("price_text"),
                                              "page_url": o.get("page_url")})
        except Exception:
            pass

    snapshot = {
        "_doc": "Product-only scrape snapshot — written when a product-specific ad is generated, "
                "so the owner can see how far the crawl reached for THIS product. Grounded: every "
                "entry is a real crawled page / real site image / extracted offering.",
        "product": {"name": product_name, "image": product_image or "",
                    "picked_from": str(mp)},
        "generation": {"kind": kind, "requested_at": datetime.now(timezone.utc).isoformat(),
                       "out_asset": out_asset},
        "coverage": {
            "reached_product_page": any(p["url_match"] for p in pages_matched),
            "text_blocks_mentioning_product": mention_blocks,
            "images_matched": len(images_matched),
            "priced_offering_found": any(o.get("price_text") for o in offerings_matched),
        },
        "pages_matched": pages_matched[:25],
        "images_matched": images_matched[:12],
        "offerings_matched": offerings_matched[:12],
    }
    fname = "product_scrape_" + (re.sub(r"[^\w؀-ۿ]+", "-", product_name.lower()).strip("-")
                                 or "product") + ".json"
    out_path = mp.parent / fname
    try:
        out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return None
    return out_path


# Notes worth surfacing in the Scraper-QA panel (capabilities/limits the owner cares about).
_QA_NOTE_KEYS = ("ajax_modal", "e-commerce", "ecommerce", "product", "budget", "sitemap",
                 "root_anchor", "deep", "readiness")


def scrape_qa_for_slug(slug: str, *, scrapes_dir: str = "scrapes") -> dict | None:
    """A compact QUALITY summary of a brand's freshest scrape — so the owner can verify the scraper
    at a glance (pages, products, images, text coverage, readiness, and the notable notes such as the
    url-less-modal resolution). None when there is no manifest. Never raises."""
    mp = _latest_manifest(slug, scrapes_dir)
    if not mp:
        return None
    try:
        m = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:
        return None
    sm = m.get("scrape_meta") or {}
    rd = m.get("readiness") or {}
    pages = m.get("pages") or []
    notes = [n for n in (m.get("notes") or []) if isinstance(n, str)]
    text_blocks = sum(len(p.get("text_blocks") or []) for p in pages if isinstance(p, dict))
    products = products_from_manifest(m, limit=100)
    key_notes = [n for n in notes if any(k in n.lower() for k in _QA_NOTE_KEYS)]
    return {
        "manifest_path": str(mp),
        "final_url": sm.get("final_url") or "",
        "pages_attempted": int(sm.get("pages_attempted") or 0),
        "pages_succeeded": int(sm.get("pages_succeeded") or 0),
        "duration_ms": int(sm.get("duration_ms") or 0),
        "budget_exceeded": bool(sm.get("budget_exceeded")),
        "ready": bool(rd.get("ready_for_extraction")),
        "major_missing": list(rd.get("major_missing") or [])[:8],
        "text_blocks": text_blocks,
        "images": len(m.get("images_of_interest") or []),
        "products": len(products),
        "failures": len(m.get("failures") or []),
        "pages": [{"url": (p.get("url") or p.get("final_url") or ""),
                   "blocks": len(p.get("text_blocks") or [])}
                  for p in pages if isinstance(p, dict)][:25],
        "key_notes": key_notes[:10],
    }
