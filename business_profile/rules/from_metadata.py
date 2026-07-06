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
from urllib.parse import urlparse

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


def _registrable_label(url: Optional[str]) -> str:
    """The site's main domain label, alnum-lowercased ('rawafrican.net' -> 'rawafrican',
    'www.orange.eg' -> 'orange'). A SOFT signal for which title/og segment is the brand."""
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.split("@")[-1].split(":")[0].lower()
    except Exception:
        return ""
    host = host[4:] if host.startswith("www.") else host
    parts = [p for p in host.split(".") if p]
    label = parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")
    return re.sub(r"[^a-z0-9]", "", label)


def _dom_hits(segment: str, dom_label: str) -> int:
    """How many of a segment's words (len>=3) appear inside the domain label — the brand
    segment echoes the domain ('Raw African' -> rawafrican), a tagline usually doesn't."""
    if not dom_label:
        return 0
    toks = re.findall(r"[a-z0-9]+", segment.lower())
    return sum(1 for t in toks if len(t) >= 3 and t in dom_label)


def _strip_possessive_descriptor(segment: str, dom_label: str) -> str:
    """'Raw African's Beauty Hub' -> 'Raw African' — but ONLY when (a) there is a real DESCRIPTOR
    after the possessive and (b) the text before the possessive reconstructs the domain label
    EXACTLY. Both guards matter: (a) keeps possessive brands whose name ends at the "'s"
    (McDonald's, Levi's) intact — nothing trails, nothing to trim; (b) keeps qualifiers
    ('Orange Egypt') and unrelated names untouched."""
    if not dom_label:
        return segment
    m = re.match(r"(.+?)['’]s\b(.*)$", segment)
    if m and m.group(2).strip():                       # a "Brand's <descriptor>" shape
        head = m.group(1).strip()
        if head and re.sub(r"[^a-z0-9]", "", head.lower()) == dom_label:
            return head
    return segment


def _pick_brand_segment(text: Optional[str], dom_label: str, *,
                        legacy_shortest: bool) -> Optional[str]:
    """Split a separator-joined name ('Brand - Tagline', 'Brand | Category, Category') and
    return the BRAND segment. A site glues its tagline/category onto og:site_name or <title>;
    taking it verbatim made the brand name a whole marketing sentence (MEASURED: rawafrican.net
    name = "Raw African's Beauty Hub - Get the Raw Experience!"). The brand is the segment that
    ECHOES the domain; with no domain signal, the FIRST segment for og:site_name (brand-first
    convention) or the SHORTEST for a <title> (the legacy heuristic). A name with no separator
    is returned untouched (only possessive-descriptor trimming may apply)."""
    if not text:
        return text
    parts = [p.strip() for p in _TITLE_SEPARATORS.split(text) if p.strip()]
    parts = [p for p in parts if p.lower() not in _GENERIC_TITLE_SEGMENTS]
    if not parts:
        return text.strip() or None
    if len(parts) == 1:
        return _strip_possessive_descriptor(parts[0], dom_label)
    # domain-echoing segment wins; -i makes the EARLIER segment win ties (never compares strings)
    best_hits, _, best_seg = max((_dom_hits(p, dom_label), -i, p) for i, p in enumerate(parts))
    if best_hits > 0:
        chosen = best_seg
    elif legacy_shortest:
        chosen = min(parts, key=lambda p: (len(p), parts.index(p)))
    else:
        chosen = parts[0]
    return _strip_possessive_descriptor(chosen, dom_label)


def extract_name_from_metadata(manifest: ScrapeManifest) -> EvidencedField[str]:
    """Extract business name from og:site_name → title → h1 in that order."""
    md = manifest.site_metadata
    home_url = manifest.scrape_meta.final_url or manifest.scrape_meta.normalized_url
    dom_label = _registrable_label(home_url)

    # 1. og:site_name (high confidence, structural)
    if md.og_site_name and md.og_site_name.strip():
        # Pick the brand segment out of a "Brand - Tagline" og:site_name (MEASURED:
        # rawafrican.net -> "Raw African"), then strip trailing/leading chrome at the SOURCE
        # ("Qasr Elkbabgi Website" -> "Qasr Elkbabgi"). The verbatim og:site_name stays the quote.
        cleaned = _strip_chrome(_pick_brand_segment(
            md.og_site_name.strip(), dom_label, legacy_shortest=False))
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
        cleaned = _strip_chrome(_pick_brand_segment(
            md.title, dom_label, legacy_shortest=True))
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
