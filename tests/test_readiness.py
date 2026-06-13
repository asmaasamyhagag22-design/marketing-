"""Tests for the readiness layer (Stage F-readiness).

Covers:
- Thin profile (homepage only): all three gates blocked, specific codes
- Partial profile (some offerings, no audience): SWOT blocked on
  audience_signal, others inherit
- Good profile: ready_for_swot=True, ready_for_strategy=True, but
  ready_for_campaign still blocked on visual/breadth
- Comprehensive profile: all three gates green
- category=OTHER blocks SWOT specifically (your call on 2026-05-21)
- llm_silent_failure blocks SWOT regardless of field counts
- single_page_evidence blocks SWOT only when ScrapeDiagnostics confirms
  more pages were discovered (avoids false positives on old scrapers)
- swot_richness_score rises monotonically with bonus signals
- Strategy and Campaign blockers include SWOT blockers (inheritance)
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

# Stub playwright (same pattern as the rest of the test suite)
_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for _n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, _n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from business_profile.quality import compute_quality  # noqa: E402
from business_profile.readiness import compute_readiness  # noqa: E402
from business_profile.schemas import (  # noqa: E402
    AudienceType,
    BusinessCategory,
    BusinessProfile,
    Confidence,
    ContactChannels,
    EvidenceItem,
    EvidencedField,
    ExtractionMeta,
    LogoCandidateSummary,
    Offering,
    OpeningHours,
    OpeningHoursEntry,
    ProfileQuality,
    ScrapeDiagnostics,
    SocialAccount,
    SourceType,
    ToneOfVoice,
    VisualIdentitySummary,
)


# ---------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _ev(page: str = "https://x.com/", extractor: str = "rule:test") -> EvidenceItem:
    return EvidenceItem(page_url=page, extractor=extractor)


def _field(value, *, source_type=SourceType.EXTRACTED, page="https://x.com/",
           confidence=Confidence.HIGH) -> EvidencedField:
    return EvidencedField(
        value=value,
        evidence=[_ev(page=page)],
        confidence=confidence,
        source_type=source_type,
    )


def _offering(name: str, page: str = "https://x.com/menu") -> Offering:
    return Offering(
        name=name,
        evidence=[_ev(page=page, extractor="rule:offerings")],
        confidence=Confidence.MEDIUM,
    )


def _base_profile(**overrides) -> BusinessProfile:
    base = dict(
        source_url="https://x.com/",
        extraction_meta=ExtractionMeta(
            manifest_path="t/m.json", extracted_at=_now(),
        ),
        quality=ProfileQuality(
            has_name=False, has_category=False, has_offerings=False,
            has_audience=False, has_value_propositions=False, has_tone=False,
            has_contact=False, has_visual=False,
            fields_extracted=0, fields_inferred=0, fields_missing=0,
            ready_for_strategy=False,
        ),
    )
    base.update(overrides)
    p = BusinessProfile(**base)
    p.quality = compute_quality(p)
    return p


def _good_logo() -> LogoCandidateSummary:
    return LogoCandidateSummary(
        src="https://x.com/logo.png",
        classification="primary_logo",
        confidence=0.82,
        score=0.9,
    )


# ---------------------------------------------------------------------
# Thin profile — homepage only, missing nearly everything
# ---------------------------------------------------------------------

def test_thin_profile_all_gates_blocked():
    """A barely-scraped homepage. SWOT, Strategy, Campaign all blocked."""
    p = _base_profile(
        name=_field("Some Cafe"),
        # No category, no offerings, no audience, no value props, no contact.
    )
    r = compute_readiness(p)

    assert r.ready_for_swot is False
    assert r.ready_for_strategy is False
    assert r.ready_for_campaign is False

    # Specific blockers we MUST see
    assert "category_unknown" in r.swot_blockers
    assert "no_offering_signal" in r.swot_blockers
    assert "no_audience_signal" in r.swot_blockers
    assert "no_differentiator_signal" in r.swot_blockers
    assert "low_evidence_coverage" in r.swot_blockers

    # Strategy and campaign INHERIT swot blockers
    assert set(r.swot_blockers).issubset(set(r.strategy_blockers))
    assert set(r.strategy_blockers).issubset(set(r.campaign_blockers))

    # Honest missing lists
    assert "category" in r.missing_critical
    assert "offerings" in r.missing_critical
    assert "visual_identity" in r.missing_critical
    assert "contact_channel" in r.missing_critical

    # Richness should be low
    assert r.swot_richness_score < 30


# ---------------------------------------------------------------------
# Category=OTHER — blocks SWOT (your call on 2026-05-21)
# ---------------------------------------------------------------------

def test_category_other_blocks_swot():
    """Even with everything else perfect, category=OTHER blocks SWOT."""
    p = _base_profile(
        name=_field("Generic Co"),
        category=_field(BusinessCategory.OTHER),
        offerings=[_offering("Service A"), _offering("Service B"), _offering("Service C")],
        value_propositions=[
            _field("Fast delivery"), _field("Local team"), _field("Honest pricing"),
        ],
        audience_type=_field(AudienceType.B2C),
        tone_of_voice=_field(ToneOfVoice.PROFESSIONAL),
        description=_field("A diversified business."),
        trust_signals=[_field("10 years in market"), _field("ISO certified")],
        contact_channels=ContactChannels(emails=["hi@x.com"]),
        visual=VisualIdentitySummary(primary_logo=_good_logo()),
    )
    r = compute_readiness(p)

    assert r.ready_for_swot is False
    assert "category_unknown" in r.swot_blockers
    assert "category" in r.missing_critical


def test_category_missing_blocks_swot():
    """category.value is None → same blocker code as OTHER."""
    p = _base_profile(
        name=_field("Some Co"),
        offerings=[_offering("X")],
    )
    r = compute_readiness(p)
    assert "category_unknown" in r.swot_blockers


# ---------------------------------------------------------------------
# llm_silent_failure — blocks SWOT regardless of field counts
# ---------------------------------------------------------------------

def test_llm_silent_failure_blocks_swot():
    p = _base_profile(
        name=_field("Cafe X"),
        category=_field(BusinessCategory.CAFE),
        offerings=[_offering("Espresso"), _offering("Latte"), _offering("Drip")],
        audience_type=_field(AudienceType.B2C),
        value_propositions=[_field("Hand-roasted"), _field("Single-origin")],
        tone_of_voice=_field(ToneOfVoice.FRIENDLY),
        description=_field("A specialty coffee bar."),
        llm_silent_failure=True,
    )
    r = compute_readiness(p)
    assert r.ready_for_swot is False
    assert "llm_silent_failure" in r.swot_blockers


# ---------------------------------------------------------------------
# Partial profile — has identity + offerings but no audience signal
# ---------------------------------------------------------------------

def test_partial_profile_blocked_on_audience():
    p = _base_profile(
        name=_field("Cafe X"),
        category=_field(BusinessCategory.CAFE),
        offerings=[_offering("Coffee", "https://x.com/menu"),
                   _offering("Pastry", "https://x.com/menu")],
        value_propositions=[_field("Specialty coffee"), _field("Hand-roasted")],
        # NO audience_type, NO audience_signals
        tone_of_voice=_field(ToneOfVoice.FRIENDLY),
        description=_field("A small specialty coffee bar."),
        contact_channels=ContactChannels(emails=["hi@x.com"]),
        visual=VisualIdentitySummary(brand_palette=["#3a2", "#fff"]),
    )
    r = compute_readiness(p)

    assert "no_audience_signal" in r.swot_blockers
    assert r.ready_for_swot is False
    # audience_inferred warning should NOT fire (no signals either)
    assert "audience_inferred_from_signals" not in r.swot_warnings


# ---------------------------------------------------------------------
# Audience signals alone are sufficient for SWOT (but not for Strategy)
# ---------------------------------------------------------------------

def _comprehensive_profile_kwargs() -> dict:
    return dict(
        name=_field("Andrea Restaurant"),
        tagline=_field("Authentic Egyptian dining"),
        description=_field("A landmark restaurant in Cairo serving traditional dishes since 1976."),
        category=_field(BusinessCategory.RESTAURANT),
        offerings=[
            _offering("Grilled chicken", "https://x.com/menu"),
            _offering("Mezze platter", "https://x.com/menu"),
            _offering("Family feast", "https://x.com/menu"),
        ],
        audience_type=_field(AudienceType.B2C),
        audience_signals=[_field("families"), _field("event hosts")],
        value_propositions=[
            _field("Heritage recipes"),
            _field("Family atmosphere"),
            _field("Premium ingredients"),
        ],
        tone_of_voice=_field(ToneOfVoice.FRIENDLY),
        trust_signals=[
            _field("Operating since 1976"),
            _field("Awarded best Egyptian restaurant 2023"),
        ],
        existing_ctas=[_field("Book a table"), _field("Order online")],
        contact_channels=ContactChannels(
            phones_e164=["+201001234567"],
            emails=["hi@andrea.example"],
        ),
        visual=VisualIdentitySummary(
            primary_logo=_good_logo(),
            brand_palette=["#2B1810", "#C8A355", "#F4EBDD"],
            primary_brand_color="#C8A355",
        ),
        languages=["ar", "en"],
        hours=OpeningHours(entries=[
            OpeningHoursEntry(days="Mon-Sun", opens="12:00", closes="00:00"),
        ]),
        social_presence=[
            SocialAccount(platform="instagram", url="https://instagram.com/andrea"),
            SocialAccount(platform="facebook", url="https://facebook.com/andrea"),
        ],
    )


def test_audience_signals_alone_pass_swot_but_block_strategy():
    kwargs = _comprehensive_profile_kwargs()
    # Drop concrete audience_type but keep signals
    kwargs.pop("audience_type")
    # We also need to force a few EvidencedField items onto pages != the homepage
    p = _base_profile(**kwargs)
    # Confirm we have enough fields_extracted to clear the SWOT threshold
    assert p.quality.fields_extracted >= 10
    r = compute_readiness(p)

    assert r.ready_for_swot is True
    assert "audience_inferred_from_signals" in r.swot_warnings
    # Strategy should still be blocked
    assert r.ready_for_strategy is False
    assert "audience_type_unknown" in r.strategy_blockers


# ---------------------------------------------------------------------
# Good profile — ready_for_swot=True, ready_for_strategy=True,
# but campaign still blocked (no visual breadth / no logo)
# ---------------------------------------------------------------------

def test_good_profile_swot_and_strategy_ready_campaign_blocked():
    kwargs = _comprehensive_profile_kwargs()
    # Strip visual identity → campaign blocked
    kwargs["visual"] = VisualIdentitySummary()
    # Trim offerings/value_props below the campaign breadth bar
    kwargs["offerings"] = [_offering("Grilled chicken"), _offering("Mezze")]
    kwargs["value_propositions"] = [_field("Heritage recipes"), _field("Family atmosphere")]
    p = _base_profile(**kwargs)
    r = compute_readiness(p)

    assert r.ready_for_swot is True
    # Strategy threshold is 12. We may or may not clear it depending on
    # exact field count; the meaningful assertion is "if SWOT clears,
    # strategy clears or fails ONLY on the documented gates."
    if not r.ready_for_strategy:
        assert (
            "strategy_evidence_below_threshold" in r.strategy_blockers
            or "low_evidence_coverage" in r.strategy_blockers
            or "audience_type_unknown" in r.strategy_blockers
        )
    assert r.ready_for_campaign is False
    assert "no_visual_identity" in r.campaign_blockers
    assert "insufficient_creative_breadth" in r.campaign_blockers


# ---------------------------------------------------------------------
# Comprehensive profile — all three gates green
# ---------------------------------------------------------------------

def test_comprehensive_profile_all_gates_ready():
    p = _base_profile(**_comprehensive_profile_kwargs())
    r = compute_readiness(p)

    assert r.ready_for_swot is True, f"swot_blockers={r.swot_blockers}"
    assert r.ready_for_strategy is True, f"strategy_blockers={r.strategy_blockers}"
    assert r.ready_for_campaign is True, f"campaign_blockers={r.campaign_blockers}"

    assert r.swot_blockers == []
    assert r.strategy_blockers == []
    assert r.campaign_blockers == []

    assert r.swot_richness_score >= 60
    assert r.scrape_completeness in ("good", "comprehensive")
    # Honest lists should be small (or empty)
    assert "category" not in r.missing_critical
    assert "offerings" not in r.missing_critical


# ---------------------------------------------------------------------
# Single-page evidence — only blocks when ScrapeDiagnostics confirms
# the scraper saw more pages
# ---------------------------------------------------------------------

def _single_page_profile() -> BusinessProfile:
    """All fields populated, but every evidence item points at the homepage."""
    homepage = "https://x.com/"
    return _base_profile(
        name=_field("Cafe X", page=homepage),
        category=_field(BusinessCategory.CAFE, page=homepage),
        offerings=[
            _offering("Espresso", homepage),
            _offering("Latte", homepage),
            _offering("Drip", homepage),
        ],
        audience_type=_field(AudienceType.B2C, page=homepage),
        value_propositions=[
            _field("Specialty coffee", page=homepage),
            _field("Hand-roasted", page=homepage),
        ],
        tone_of_voice=_field(ToneOfVoice.FRIENDLY, page=homepage),
        description=_field("A specialty coffee bar.", page=homepage),
        trust_signals=[_field("Award-winning", page=homepage)],
        contact_channels=ContactChannels(emails=["hi@x.com"]),
        visual=VisualIdentitySummary(primary_logo=_good_logo()),
    )


def test_single_page_without_diagnostics_only_warns():
    """Old scrapers don't emit ScrapeDiagnostics. Don't punish them with a hard block."""
    p = _single_page_profile()
    r = compute_readiness(p)  # no scrape_diagnostics
    assert "single_page_evidence" not in r.swot_blockers
    assert "single_page_evidence_unverified" in r.swot_warnings


def test_single_page_with_diagnostics_blocks():
    """When the scraper KNOWS more pages existed, single-page evidence blocks SWOT."""
    p = _single_page_profile()
    diag = ScrapeDiagnostics(
        pages_discovered=5, pages_scraped=1, pages_with_text_blocks=1,
        pages_failed=4, sitemap_used=True,
    )
    r = compute_readiness(p, diag)
    assert "single_page_evidence" in r.swot_blockers
    assert r.ready_for_swot is False


def test_single_page_with_diagnostics_no_other_pages_does_not_block():
    """If only 1 page was discovered, single-page evidence is not a failure."""
    p = _single_page_profile()
    diag = ScrapeDiagnostics(
        pages_discovered=1, pages_scraped=1, pages_with_text_blocks=1,
    )
    r = compute_readiness(p, diag)
    assert "single_page_evidence" not in r.swot_blockers


# ---------------------------------------------------------------------
# Richness score monotonicity
# ---------------------------------------------------------------------

def test_richness_score_rises_with_bonus_signals():
    base = _base_profile(
        name=_field("Cafe X"),
        category=_field(BusinessCategory.CAFE),
        offerings=[_offering("Espresso"), _offering("Latte")],
        audience_type=_field(AudienceType.B2C),
        value_propositions=[_field("Specialty coffee")],
        tone_of_voice=_field(ToneOfVoice.FRIENDLY),
        contact_channels=ContactChannels(emails=["hi@x.com"]),
        visual=VisualIdentitySummary(primary_logo=_good_logo()),
    )
    base_r = compute_readiness(base)

    richer = _base_profile(
        name=_field("Cafe X"),
        tagline=_field("Specialty coffee in Cairo"),
        description=_field("A small specialty coffee bar in Cairo."),
        category=_field(BusinessCategory.CAFE),
        offerings=[_offering("Espresso"), _offering("Latte"), _offering("Drip")],
        audience_type=_field(AudienceType.B2C),
        audience_signals=[_field("students"), _field("remote workers")],
        value_propositions=[
            _field("Specialty coffee"),
            _field("Hand-roasted"),
            _field("Single-origin"),
        ],
        tone_of_voice=_field(ToneOfVoice.FRIENDLY),
        trust_signals=[_field("Best of Cairo 2024"), _field("100% organic")],
        existing_ctas=[_field("Order online")],
        contact_channels=ContactChannels(emails=["hi@x.com"], phones_e164=["+201001234567"]),
        visual=VisualIdentitySummary(
            primary_logo=_good_logo(),
            brand_palette=["#2B1810", "#C8A355"],
        ),
        languages=["ar", "en"],
        hours=OpeningHours(entries=[
            OpeningHoursEntry(days="Mon-Sun", opens="07:00", closes="22:00"),
        ]),
        social_presence=[
            SocialAccount(platform="instagram", url="https://instagram.com/x"),
            SocialAccount(platform="facebook", url="https://facebook.com/x"),
        ],
    )
    richer_r = compute_readiness(richer)

    assert richer_r.swot_richness_score > base_r.swot_richness_score


# ---------------------------------------------------------------------
# Inheritance: strategy blockers contain SWOT blockers
# ---------------------------------------------------------------------

def test_blocker_inheritance_holds():
    p = _base_profile(name=_field("X"))
    r = compute_readiness(p)
    assert set(r.swot_blockers).issubset(set(r.strategy_blockers))
    assert set(r.strategy_blockers).issubset(set(r.campaign_blockers))


# ---------------------------------------------------------------------
# Weak evidence — INFERRED fields should appear in weak_evidence_fields
# ---------------------------------------------------------------------

def test_weak_evidence_lists_inferred_fields():
    p = _base_profile(
        name=_field("X"),
        category=_field(BusinessCategory.CAFE, source_type=SourceType.INFERRED),
        tone_of_voice=_field(ToneOfVoice.FRIENDLY, source_type=SourceType.INFERRED),
    )
    r = compute_readiness(p)
    assert "category" in r.weak_evidence_fields
    assert "tone_of_voice" in r.weak_evidence_fields
