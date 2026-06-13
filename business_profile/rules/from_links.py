"""Links-derived fields: social_presence and existing_ctas.

Social: dedupe by URL, one SocialAccount per platform+url.
CTAs: each cta_candidate becomes an EvidencedField[str] with the
anchor text as value.
"""
from __future__ import annotations

from scraper.schemas import ScrapeManifest

from ..schemas import (
    Confidence,
    EvidenceItem,
    EvidencedField,
    SocialAccount,
    SourceType,
)


def extract_social_presence(manifest: ScrapeManifest) -> list[SocialAccount]:
    out: list[SocialAccount] = []
    seen_urls: set[str] = set()

    for link in manifest.links.social:
        url = link.href
        if url in seen_urls:
            continue
        seen_urls.add(url)
        out.append(SocialAccount(
            platform=link.platform or "unknown",
            url=url,
            evidence=[EvidenceItem(
                block_id=link.block_id,
                page_url=link.page_url,
                quote=link.anchor_text or url,
                extractor="rule:social_link",
            )],
        ))
    return out


def extract_existing_ctas(manifest: ScrapeManifest) -> list[EvidencedField[str]]:
    out: list[EvidencedField[str]] = []
    seen_anchors: set[str] = set()

    for link in manifest.links.cta_candidates:
        anchor = (link.anchor_text or "").strip()
        if not anchor:
            continue
        key = anchor.lower()
        if key in seen_anchors:
            continue
        seen_anchors.add(key)

        out.append(EvidencedField(
            value=anchor,
            evidence=[EvidenceItem(
                block_id=link.block_id,
                page_url=link.page_url,
                quote=anchor,
                extractor="rule:cta_anchor",
            )],
            confidence=Confidence.HIGH,
            source_type=SourceType.EXTRACTED,
        ))
    return out
