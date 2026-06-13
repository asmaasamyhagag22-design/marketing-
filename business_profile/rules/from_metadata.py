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

_TITLE_SEPARATORS = re.compile(r"\s*[|–—·•]\s*|\s+[-]\s+", re.UNICODE)


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
        return EvidencedField(
            value=md.og_site_name.strip(),
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
        cleaned = _clean_title(md.title)
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
