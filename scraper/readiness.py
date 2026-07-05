"""Readiness report.

Roll up the manifest into a small set of booleans that downstream
stages can use as a precondition. If `ready_for_extraction` is False,
the pipeline can stop here with a clear error instead of producing
hallucinated outputs from a thin scrape.
"""
from __future__ import annotations

from .schemas import PageType, ReadinessReport, ScrapeManifest


def _homepage_is_usable(p) -> bool:
    """H8: a homepage counts for readiness if it carries real content — even if its ONLY
    failure is the benign timeout-partial-content salvage.

    The salvage exists precisely to KEEP a homepage whose useful DOM loaded before a late
    asset timed out; the old `not p.failures` test threw that content away and aborted the
    whole pipeline (MEASURED: nahdi with 226 homepage text blocks and te.eg with 87 were
    marked not-ready and discarded). A HARD-failed homepage (bot wall / empty DOM /
    network) never becomes a HOMEPAGE PageRecord — it is recorded as a manifest failure
    and the crawl returns early upstream — so the ONLY failure that can sit on a HOMEPAGE
    record is the salvage TIMEOUT. Requiring real content here still correctly rejects an
    empty salvage (buffaloburger: 0 blocks -> stays not-ready)."""
    if p.page_type != PageType.HOMEPAGE:
        return False
    return bool(getattr(p, "text_blocks", None)) or bool(getattr(p, "cleaned_main_text", None))


def compute_readiness(m: ScrapeManifest) -> ReadinessReport:
    pages = m.pages or []

    has_homepage = any(_homepage_is_usable(p) for p in pages)

    has_internal_pages = any(
        p.page_type != PageType.HOMEPAGE and not p.failures for p in pages
    )

    has_contact_signals = bool(
        m.contact.phones or m.contact.emails or m.contact.whatsapp
        or m.contact.map_embeds or m.contact.addresses_raw
    )

    has_visual_signals = bool(
        m.visual.primary_logo
        or m.visual.logo
        or m.visual.brand_palette
        or m.visual.primary_brand_color
        or m.visual.color_palette  # legacy fallback
        or (m.visual.fonts and any(m.visual.fonts.values()))
    )

    has_cta_candidates = bool(m.links.cta_candidates)

    has_metadata = bool(
        m.site_metadata.title or m.site_metadata.description
        or m.site_metadata.og_title or m.site_metadata.schema_org
    )

    missing: list[str] = []
    if not has_homepage:
        missing.append("homepage")
    if not has_internal_pages:
        missing.append("internal_pages")
    if not has_contact_signals:
        missing.append("contact_signals")
    if not has_visual_signals:
        missing.append("visual_signals")
    if not has_cta_candidates:
        missing.append("cta_candidates")
    if not has_metadata:
        missing.append("metadata")

    # The bare minimum for downstream extraction is a homepage + some
    # form of contact or visual signal.
    ready = has_homepage and (has_contact_signals or has_visual_signals or has_metadata)

    return ReadinessReport(
        has_homepage=has_homepage,
        has_internal_pages=has_internal_pages,
        has_contact_signals=has_contact_signals,
        has_visual_signals=has_visual_signals,
        has_cta_candidates=has_cta_candidates,
        has_metadata=has_metadata,
        major_missing=missing,
        ready_for_extraction=ready,
    )
