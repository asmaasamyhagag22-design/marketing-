"""Site metadata extraction.

Reads:
- <title>, <meta name="description">, <meta name="keywords">
- Open Graph and Twitter Card tags
- <link rel="canonical">, <link rel="icon">
- <html lang="...">
- schema.org JSON-LD blocks

Works on rendered HTML (string), not a live Page. This means it can be
re-run later from saved HTML without launching a browser.
"""
from __future__ import annotations

import json
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..schemas import SchemaOrgBlock, SiteMetadata


def _attr(el, name: str) -> Optional[str]:
    if not el:
        return None
    val = el.get(name)
    return val.strip() if isinstance(val, str) and val.strip() else None


def extract_metadata(html: str, page_url: str) -> SiteMetadata:
    if not html:
        return SiteMetadata()

    soup = BeautifulSoup(html, "lxml")
    head = soup.head or soup  # if no head, search whole doc

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    description = _attr(head.find("meta", attrs={"name": "description"}), "content")
    keywords = _attr(head.find("meta", attrs={"name": "keywords"}), "content")

    canonical = _attr(head.find("link", rel="canonical"), "href")
    favicon_el = head.find("link", rel=lambda v: v and "icon" in v.lower())
    favicon = _attr(favicon_el, "href")
    if favicon:
        favicon = urljoin(page_url, favicon)
    if canonical:
        canonical = urljoin(page_url, canonical)

    og_title = _attr(head.find("meta", property="og:title"), "content")
    og_description = _attr(head.find("meta", property="og:description"), "content")
    og_image = _attr(head.find("meta", property="og:image"), "content")
    og_site_name = _attr(head.find("meta", property="og:site_name"), "content")
    if og_image:
        og_image = urljoin(page_url, og_image)

    twitter_card = _attr(head.find("meta", attrs={"name": "twitter:card"}), "content")

    html_tag = soup.find("html")
    html_lang = _attr(html_tag, "lang")

    # schema.org JSON-LD blocks
    schema_blocks: list[SchemaOrgBlock] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            schema_blocks.append(SchemaOrgBlock(
                type=item.get("@type") if isinstance(item.get("@type"), str) else None,
                data=item,
                source="json_ld",
            ))

    # PR-2: Microdata + RDFa via extruct. Lives in a separate module so
    # extruct (which pulls in mf2py + rdflib transitively) is only
    # imported when we actually parse a page. Failures degrade
    # gracefully — never propagate up.
    try:
        from .structured_data import extract_structured_data, dedupe_schema_blocks
        schema_blocks.extend(extract_structured_data(html, page_url))
        # Cross-source dedupe: if a site emits BOTH JSON-LD AND Microdata
        # for the same business, keep one copy (highest-priority source).
        schema_blocks = dedupe_schema_blocks(schema_blocks)
    except Exception:  # pragma: no cover — defensive only
        # We already log inside extract_structured_data; nothing to do here.
        pass

    return SiteMetadata(
        title=title,
        description=description,
        keywords=keywords,
        canonical=canonical,
        favicon=favicon,
        og_title=og_title,
        og_description=og_description,
        og_image=og_image,
        og_site_name=og_site_name,
        twitter_card=twitter_card,
        html_lang=html_lang,
        schema_org=schema_blocks,
    )


def merge_metadata(primary: SiteMetadata, secondary: SiteMetadata) -> SiteMetadata:
    """Merge two metadata records, preferring primary's non-null values.

    Used to combine homepage metadata (primary) with sub-page metadata
    where useful (e.g., the Contact page might add a schema.org block
    the homepage doesn't have).
    """
    def pick(a, b):
        return a if a else b

    merged = SiteMetadata(
        title=pick(primary.title, secondary.title),
        description=pick(primary.description, secondary.description),
        keywords=pick(primary.keywords, secondary.keywords),
        canonical=pick(primary.canonical, secondary.canonical),
        favicon=pick(primary.favicon, secondary.favicon),
        og_title=pick(primary.og_title, secondary.og_title),
        og_description=pick(primary.og_description, secondary.og_description),
        og_image=pick(primary.og_image, secondary.og_image),
        og_site_name=pick(primary.og_site_name, secondary.og_site_name),
        twitter_card=pick(primary.twitter_card, secondary.twitter_card),
        html_lang=pick(primary.html_lang, secondary.html_lang),
        schema_org=_merge_schema_blocks(primary.schema_org, secondary.schema_org),
    )
    return merged


def _merge_schema_blocks(primary, secondary):
    """Concatenate two schema_org lists, then dedupe across sources.

    Without dedupe, the same business block emitted on both the
    homepage and the contact page would appear twice. PR-2 imports
    dedupe_schema_blocks from structured_data; if the import fails
    (e.g., partial install), we degrade to a plain concat.
    """
    combined = list(primary) + list(secondary)
    try:
        from .structured_data import dedupe_schema_blocks
        return dedupe_schema_blocks(combined)
    except ImportError:
        return combined