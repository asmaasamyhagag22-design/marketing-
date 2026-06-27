"""Business name from metadata.

Priority order (highest confidence first):
1. schema.org name field (handled in from_schema_org)
2. og:site_name
3. <title> (after generic-suffix cleanup)
4. Homepage h1 from text_blocks

This module covers 2–4. The orchestrator picks the highest-confidence
non-null result across this and from_schema_org.
"""
from __future__ import annotations

import re
from typing import Optional

from scraper.schemas import ScrapeManifest, PageType

from ..schemas import (
    Confidence,
    EvidenceItem,
    EvidencedField,
    SourceType,
)


# Words that are clearly not the brand. If a title segment equals one
# of these (case-insensitive), drop it.
_GENERIC_TITLE_SEGMENTS = {
    "home", "homepage", "welcome", "official site", "official website",
    "main", "index", "الرئيسية", "الصفحة الرئيسية", "ترحيب",
}

# "Chrome" words a site appends to (or prepends to) its own name in og:site_name
# or <title> — NOT part of the brand. e.g. og:site_name = "Qasr Elkbabgi Website".
# These are stripped (case-insensitive, whole-word) ONLY when something brand-like
# remains, so the SOURCE name is clean and every downstream consumer (poster, reel,
# SWOT) inherits it — not just the poster's band-aid `_clean_business_name`.
# Deliberately TIGHT: only high-confidence chrome (website/official/homepage) plus
# e-commerce SECTION designators (e-shop / online store) that big brands append to a
# sub-site's og:site_name (MEASURED: "Vodafone Egypt E-Shop" -> "Vodafone Egypt", the
# ONLY change across 48 saved names). Bare "home"/"online"/"shop"/"store" stay
# EXCLUDED — they can be legitimate brand words (verified safe: "EVA Shop" untouched).
_TRAILING_CHROME = (
    "official website", "official site", "website", "homepage", "home page",
    "official", "e-shop", "eshop", "e shop", "online shop", "online store", "webshop",
    "الموقع الرسمي", "الموقع الالكتروني", "الموقع الإلكتروني",
)
_LEADING_CHROME = (
    "welcome to the", "welcome to", "official website of", "official site of",
)

_TITLE_SEPARATORS = re.compile(r"\s*[|–—·•]\s*|\s+[-]\s+", re.UNICODE)

# Separators/punctuation a chrome word might be glued to the brand with.
_CHROME_EDGE = " -–—:|·•"


def _strip_chrome(name: Optional[str]) -> Optional[str]:
    """Remove trailing/leading generic 'chrome' words from a brand name.

    Conservative: a chrome word is removed only as a whole leading/trailing token
    AND only when a non-empty brand remains (so a name that IS just chrome is kept
    verbatim rather than emptied). Runs to a fixed point so "Brand Official Website"
    collapses fully. Returns the input unchanged when nothing matches.
    """
    if not name:
        return name
    s = " ".join(name.split())
    changed = True
    while changed and s:
        changed = False
        low = s.lower()
        for w in _LEADING_CHROME:
            if low.startswith(w + " "):
                cand = s[len(w):].strip(_CHROME_EDGE)
                if cand:
                    s, changed = cand, True
                break
        if changed:
            continue
        low = s.lower()
        for w in _TRAILING_CHROME:
            if low == w:
                break  # the whole name is chrome — keep it, don't empty it
            if low.endswith(" " + w):
                cand = s[: len(s) - len(w)].strip(_CHROME_EDGE)
                if cand:
                    s, changed = cand, True
                break
    return s


def _clean_title(title: str) -> Optional[str]:
    """Heuristic: split on common separators, drop generic segments,
    return the shortest meaningful one (usually the brand)."""
    if not title:
        return None
    parts = [p.strip() for p in _TITLE_SEPARATORS.split(title) if p.strip()]
    parts = [p for p in parts if p.lower() not in _GENERIC_TITLE_SEGMENTS]
    if not parts:
        return title.strip() or None
    # Shortest is usually the brand; tiebreak by first occurrence.
    # Capture original index BEFORE sort to avoid mutating-during-sort bugs.
    indexed = list(enumerate(parts))
    indexed.sort(key=lambda iv: (len(iv[1]), iv[0]))
    return indexed[0][1]


def extract_name_from_metadata(manifest: ScrapeManifest) -> EvidencedField[str]:
    """Extract business name from og:site_name → title → h1 in that order."""
    md = manifest.site_metadata
    home_url = manifest.scrape_meta.final_url or manifest.scrape_meta.normalized_url

    # 1. og:site_name (high confidence, structural)
    if md.og_site_name and md.og_site_name.strip():
        # Strip trailing/leading chrome at the SOURCE ("Qasr Elkbabgi Website"
        # -> "Qasr Elkbabgi"). The verbatim og:site_name is still the cited quote.
        cleaned = _strip_chrome(md.og_site_name.strip())
        return EvidencedField(
            value=cleaned,
            evidence=[EvidenceItem(
                block_id=None, page_url=home_url,
                quote=md.og_site_name.strip(),
                extractor="rule:og:site_name",
            )],
            confidence=Confidence.HIGH,
            source_type=SourceType.EXTRACTED,
        )

    # 2. <title> cleaned
    if md.title:
        cleaned = _strip_chrome(_clean_title(md.title))
        if cleaned:
            return EvidencedField(
                value=cleaned,
                evidence=[EvidenceItem(
                    block_id=None, page_url=home_url,
                    quote=md.title,
                    extractor="rule:title",
                )],
                # Title is less reliable than og:site_name
                confidence=Confidence.MEDIUM,
                source_type=SourceType.EXTRACTED,
            )

    # 3. First h1 on the homepage from text_blocks
    home_page = next((p for p in manifest.pages
                      if p.page_type == PageType.HOMEPAGE), None)
    if home_page:
        h1_block = next((b for b in home_page.text_blocks
                         if b.tag == "h1" and b.text and len(b.text) < 100), None)
        if h1_block:
            return EvidencedField(
                value=h1_block.text.strip(),
                evidence=[EvidenceItem(
                    block_id=h1_block.block_id,
                    page_url=h1_block.page_url,
                    quote=h1_block.text[:200],
                    extractor="rule:homepage_h1",
                )],
                # H1 is often a tagline, not a brand — lowest of the three
                confidence=Confidence.LOW,
                source_type=SourceType.EXTRACTED,
            )

    return EvidencedField.missing()
