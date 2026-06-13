"""Readiness layer (Stage F-readiness).

Pure function. Given a `BusinessProfile` (and optionally
`ScrapeDiagnostics` from the scraper), produces a `ReadinessReport`
that the API exposes to the frontend and that the SWOT/Strategy/
Campaign endpoints consult before doing any work.

Design contract:
- Pure function. No I/O. No manifest re-read. Safe to call repeatedly.
- Two-state gates only (ready / not ready). No tentative middle tier.
- All blockers are machine codes. The frontend owns translation.
- Thresholds (you agreed to these on 2026-05-21):
    ready_for_swot       requires fields_extracted >= 10
    ready_for_strategy   requires fields_extracted >= 12
    ready_for_campaign   requires fields_extracted >= 15

- SWOT is blocked when category is unknown or OTHER (your call).
- SWOT is blocked when the LLM stage silently failed.
- SWOT is blocked when evidence is from a single page AND the scraper
  reports more pages were discovered (catches "scraper bounced").
"""
from __future__ import annotations

from typing import Optional

from .schemas import (
    BusinessCategory,
    BusinessProfile,
    EvidencedField,
    ReadinessReport,
    ScrapeCompleteness,
    ScrapeDiagnostics,
    SourceType,
)


# ---------------------------------------------------------------------
# Thresholds (single source of truth)
# ---------------------------------------------------------------------

_MIN_EXTRACTED_SWOT = 10
_MIN_EXTRACTED_STRATEGY = 12
_MIN_EXTRACTED_CAMPAIGN = 15


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _state(f: EvidencedField) -> SourceType:
    """Effective state of an EvidencedField, mirroring quality.py's rule."""
    if f.value is None:
        return SourceType.MISSING
    if f.source_type == SourceType.MISSING:
        return SourceType.EXTRACTED
    return f.source_type


def _has(f: EvidencedField) -> bool:
    return f.value is not None and _state(f) != SourceType.MISSING


def _has_extracted(f: EvidencedField) -> bool:
    return f.value is not None and _state(f) == SourceType.EXTRACTED


def _contact_has_data(profile: BusinessProfile) -> bool:
    c = profile.contact_channels
    return bool(
        c.phones or c.emails or c.whatsapp_numbers
        or c.has_contact_form or c.physical_addresses or c.map_embed_present
    )


def _visual_has_data(profile: BusinessProfile) -> bool:
    v = profile.visual
    return bool(
        v.logo_url
        or v.primary_logo
        or v.primary_brand_color
        or v.brand_palette
        or v.palette_hex
    )


def _confident_logo(profile: BusinessProfile) -> bool:
    v = profile.visual
    if v.primary_logo and v.primary_logo.confidence >= 0.55:
        return True
    if v.brand_palette:
        return True
    if v.palette_hex and len(v.palette_hex) >= 2:
        return True
    return False


def _distinct_evidence_pages(profile: BusinessProfile) -> int:
    """Count distinct page_urls across every evidence item in the profile.

    Walks every field that carries evidence. This is the honest answer to
    'how many pages of this site actually produced facts?' which is the
    real signal for SWOT trustworthiness.
    """
    urls: set[str] = set()

    def _scan_evidence(items):
        for ev in items or []:
            if ev.page_url:
                urls.add(ev.page_url)

    # Scalar EvidencedFields
    for f in (
        profile.name, profile.tagline, profile.description, profile.category,
        profile.pricing_visible, profile.pricing_posture,
        profile.audience_type, profile.tone_of_voice,
    ):
        _scan_evidence(getattr(f, "evidence", []))

    # Lists of EvidencedFields
    for lst in (
        profile.audience_signals, profile.value_propositions,
        profile.trust_signals, profile.existing_ctas, profile.service_areas,
    ):
        for f in lst:
            _scan_evidence(getattr(f, "evidence", []))

    # Lists of structured objects with .evidence
    for items in (profile.offerings, profile.locations, profile.social_presence):
        for item in items:
            _scan_evidence(getattr(item, "evidence", []))

    # Sections with their own evidence
    _scan_evidence(getattr(profile.contact_channels, "evidence", []))
    if profile.hours:
        _scan_evidence(getattr(profile.hours, "evidence", []))

    return len(urls)


def _completeness(extracted: int) -> ScrapeCompleteness:
    if extracted >= 15:
        return "comprehensive"
    if extracted >= 12:
        return "good"
    if extracted >= 8:
        return "partial"
    return "thin"


# ---------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------

def compute_readiness(
    profile: BusinessProfile,
    scrape_diagnostics: Optional[ScrapeDiagnostics] = None,
) -> ReadinessReport:
    """Compute the per-stage readiness report.

    Pure. No I/O. Safe to call from the API hot path.
    """
    q = profile.quality

    # ------------------- Field-level booleans -------------------
    # SWOT must rest on EXTRACTED identity, not LLM-inferred.
    has_name = _has_extracted(profile.name)
    # Category may be EXTRACTED or INFERRED, but must not be UNKNOWN/OTHER.
    category_known = (
        profile.category.value is not None
        and _state(profile.category) != SourceType.MISSING
        and profile.category.value != BusinessCategory.OTHER
    )
    has_offerings = len(profile.offerings) >= 1
    has_offerings_2 = len(profile.offerings) >= 2
    has_offerings_3 = len(profile.offerings) >= 3
    has_value_props = len(profile.value_propositions) >= 1
    has_value_props_2 = len(profile.value_propositions) >= 2
    has_value_props_3 = len(profile.value_propositions) >= 3
    has_audience_type = (
        profile.audience_type.value is not None
        and _state(profile.audience_type) != SourceType.MISSING
        and str(profile.audience_type.value).lower() != "unknown"
    )
    has_audience_signals = len(profile.audience_signals) >= 1
    has_trust = len(profile.trust_signals) >= 1
    has_trust_2 = len(profile.trust_signals) >= 2
    has_tone = (
        profile.tone_of_voice.value is not None
        and _state(profile.tone_of_voice) != SourceType.MISSING
        and str(profile.tone_of_voice.value).lower() != "unknown"
    )
    has_description = _has(profile.description)
    has_tagline = _has(profile.tagline)
    has_contact = _contact_has_data(profile)
    has_visual = _confident_logo(profile)
    has_ctas = len(profile.existing_ctas) >= 1
    has_languages = len(profile.languages) >= 1

    # Differentiator signal — broader, used for SWOT
    differentiator_signal = (
        has_value_props
        or has_trust
        or (has_tone and has_description)
    )

    # Audience signal — broader, used for SWOT
    audience_signal_present = has_audience_type or has_audience_signals

    # Offering signal — broader, used for SWOT
    offering_signal_present = (
        has_offerings_2
        or (has_description and has_value_props_2)
    )

    # ------------------- Evidence coverage -------------------
    distinct_pages = _distinct_evidence_pages(profile)
    pages_discovered = scrape_diagnostics.pages_discovered if scrape_diagnostics else 0
    pages_scraped = scrape_diagnostics.pages_scraped if scrape_diagnostics else 0

    # "Single page only" is only a blocker if we KNOW more pages existed.
    # If we don't have ScrapeDiagnostics, we still warn but don't block,
    # to avoid penalising users on early scraper versions.
    single_page_block = (
        distinct_pages < 2
        and pages_discovered >= 2  # we KNOW there were more
    )

    # ------------------- SWOT blockers -------------------
    swot_blockers: list[str] = []

    if not has_name:
        swot_blockers.append("no_name")
    if not category_known:
        # One code covers both "value is None" and "value is OTHER".
        # Frontend can branch on the category field separately if needed.
        swot_blockers.append("category_unknown")
    if not offering_signal_present:
        swot_blockers.append("no_offering_signal")
    if not audience_signal_present:
        swot_blockers.append("no_audience_signal")
    if not differentiator_signal:
        swot_blockers.append("no_differentiator_signal")
    if q.fields_extracted < _MIN_EXTRACTED_SWOT:
        swot_blockers.append("low_evidence_coverage")
    if getattr(profile, "llm_silent_failure", False):
        swot_blockers.append("llm_silent_failure")
    if single_page_block:
        swot_blockers.append("single_page_evidence")

    ready_for_swot = len(swot_blockers) == 0

    # ------------------- Strategy blockers -------------------
    # Strategy ⇒ SWOT. We require SWOT to be ready, then add strategy-specific gates.
    strategy_blockers: list[str] = list(swot_blockers)  # inherit

    if not (has_ctas or has_contact):
        strategy_blockers.append("no_cta_or_contact_path")
    if not has_tone:
        strategy_blockers.append("tone_unknown")
    if not has_audience_type:
        # SWOT accepted audience_signals alone; strategy demands a concrete type.
        strategy_blockers.append("audience_type_unknown")
    if q.fields_extracted < _MIN_EXTRACTED_STRATEGY:
        # If SWOT already raised low_evidence_coverage we don't double-up;
        # otherwise add a strategy-specific code.
        if "low_evidence_coverage" not in strategy_blockers:
            strategy_blockers.append("strategy_evidence_below_threshold")

    # Dedupe while preserving order
    strategy_blockers = list(dict.fromkeys(strategy_blockers))
    ready_for_strategy = len(strategy_blockers) == 0

    # ------------------- Campaign blockers -------------------
    campaign_blockers: list[str] = list(strategy_blockers)  # inherit

    if not has_visual:
        campaign_blockers.append("no_visual_identity")
    if not has_contact:
        campaign_blockers.append("no_reachable_contact_channel")
    if not (has_offerings_3 or has_value_props_3):
        campaign_blockers.append("insufficient_creative_breadth")
    if not has_ctas:
        campaign_blockers.append("no_existing_ctas")
    if not has_languages:
        campaign_blockers.append("no_languages_detected")
    if q.fields_extracted < _MIN_EXTRACTED_CAMPAIGN:
        if "low_evidence_coverage" not in campaign_blockers and \
           "strategy_evidence_below_threshold" not in campaign_blockers:
            campaign_blockers.append("campaign_evidence_below_threshold")

    campaign_blockers = list(dict.fromkeys(campaign_blockers))
    ready_for_campaign = len(campaign_blockers) == 0

    # ------------------- SWOT warnings (non-blocking) -------------------
    swot_warnings: list[str] = []
    if has_audience_signals and not has_audience_type:
        swot_warnings.append("audience_inferred_from_signals")
    if not has_tagline and not has_description:
        swot_warnings.append("no_brand_statement")
    if distinct_pages < 2 and not single_page_block:
        # We don't know that more pages existed; still worth flagging.
        swot_warnings.append("single_page_evidence_unverified")
    if q.fields_inferred > q.fields_extracted:
        swot_warnings.append("more_inferred_than_extracted")
    if not has_trust:
        swot_warnings.append("no_trust_signals_found")

    # ------------------- swot_richness_score -------------------
    # Bonus signals that don't gate but make SWOT richer.
    signals = {
        "tagline": has_tagline,
        "description": has_description,
        "audience_type_concrete": has_audience_type,
        "audience_signals_2plus": len(profile.audience_signals) >= 2,
        "value_propositions_3plus": has_value_props_3,
        "trust_signals_2plus": has_trust_2,
        "offerings_3plus": has_offerings_3,
        "tone_known": has_tone,
        "languages_known": has_languages,
        "social_presence_2plus": len(profile.social_presence) >= 2,
        "locations_with_geo": any(
            (loc.city or loc.country) for loc in profile.locations
        ),
        "hours_known": bool(profile.hours and profile.hours.entries),
        "pricing_posture_known": _has(profile.pricing_posture),
        "visual_palette_known": bool(profile.visual.brand_palette or profile.visual.palette_hex),
        "logo_known": bool(profile.visual.primary_logo and profile.visual.primary_logo.confidence >= 0.55),
        "multi_page_evidence": distinct_pages >= 3,
    }
    # Score: 100 * (true signals / total). Capped 0..100.
    if signals:
        score = round(100 * sum(1 for v in signals.values() if v) / len(signals))
    else:
        score = 0

    # ------------------- Honest missing/weak lists -------------------
    missing_critical: list[str] = []
    if not has_name:
        missing_critical.append("name")
    if not category_known:
        missing_critical.append("category")
    if not has_offerings:
        missing_critical.append("offerings")
    if not has_visual:
        missing_critical.append("visual_identity")
    if not has_contact:
        missing_critical.append("contact_channel")

    missing_recommended: list[str] = []
    if not has_tagline:
        missing_recommended.append("tagline")
    if not has_audience_type:
        missing_recommended.append("audience_type")
    if not has_value_props:
        missing_recommended.append("value_propositions")
    if not has_tone:
        missing_recommended.append("tone_of_voice")
    if not has_trust:
        missing_recommended.append("trust_signals")
    if not has_ctas:
        missing_recommended.append("existing_ctas")
    if not has_languages:
        missing_recommended.append("languages")
    if not (profile.hours and profile.hours.entries):
        missing_recommended.append("hours")
    if not profile.social_presence:
        missing_recommended.append("social_presence")

    weak_evidence_fields: list[str] = []
    for name, f in (
        ("category", profile.category),
        ("description", profile.description),
        ("tagline", profile.tagline),
        ("audience_type", profile.audience_type),
        ("tone_of_voice", profile.tone_of_voice),
        ("pricing_posture", profile.pricing_posture),
    ):
        if f.value is not None and _state(f) == SourceType.INFERRED:
            weak_evidence_fields.append(name)

    # ------------------- Build report -------------------
    return ReadinessReport(
        ready_for_swot=ready_for_swot,
        ready_for_strategy=ready_for_strategy,
        ready_for_campaign=ready_for_campaign,
        swot_blockers=swot_blockers,
        strategy_blockers=strategy_blockers,
        campaign_blockers=campaign_blockers,
        swot_warnings=swot_warnings,
        swot_richness_score=score,
        swot_quality_signals=signals,
        missing_critical=missing_critical,
        missing_recommended=missing_recommended,
        weak_evidence_fields=weak_evidence_fields,
        fields_extracted=q.fields_extracted,
        fields_inferred=q.fields_inferred,
        fields_missing=q.fields_missing,
        distinct_evidence_pages=distinct_pages,
        pages_discovered=pages_discovered,
        pages_scraped=pages_scraped,
        scrape_completeness=_completeness(q.fields_extracted),
    )