"""Tests for the wire between scraper.ScrapeDiagnostics and
business_profile.readiness.

The two ScrapeDiagnostics classes (scraper-side, business_profile-side)
are intentionally separate. This test confirms the adapter in
business_profile/build.py correctly bridges them, AND that the
single_page_evidence gate flips at the right boundary.

Also tests build_profile_no_llm now attaches readiness (PR-1 wiring).
"""
from __future__ import annotations

import sys
import types

_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for _n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, _n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from datetime import datetime, timezone

# scraper-side ScrapeDiagnostics (the manifest's field)
from scraper.schemas import ScrapeDiagnostics as ScraperDiagnostics  # noqa: E402

# business_profile-side ScrapeDiagnostics (input to compute_readiness)
from business_profile.schemas import (  # noqa: E402
    BusinessCategory, EvidenceItem, EvidencedField, ExtractionMeta,
    Confidence, ProfileQuality, BusinessProfile, AudienceType,
    ContactChannels, LogoCandidateSummary, Offering, SourceType,
    ToneOfVoice, VisualIdentitySummary,
)
from business_profile.quality import compute_quality  # noqa: E402
from business_profile.readiness import compute_readiness  # noqa: E402
from business_profile.build import _diagnostics_from_manifest  # noqa: E402


def _now():
    return datetime.now(timezone.utc)


def _ev(page="https://x.com/"):
    return EvidenceItem(page_url=page, extractor="rule:test")


def _field(value, page="https://x.com/"):
    return EvidencedField(
        value=value, evidence=[_ev(page)],
        confidence=Confidence.HIGH, source_type=SourceType.EXTRACTED,
    )


def _good_logo():
    return LogoCandidateSummary(
        src="https://x.com/logo.png",
        classification="primary_logo", confidence=0.82, score=0.9,
    )


def _build_full_profile_single_page() -> BusinessProfile:
    """Build a profile where every evidence item points at the homepage.

    Field-rich enough to clear the SWOT evidence threshold (>=10).
    Used to test that ScrapeDiagnostics can flip `single_page_evidence`.
    """
    home = "https://x.com/"
    p = BusinessProfile(
        source_url=home,
        extraction_meta=ExtractionMeta(manifest_path="t/m.json", extracted_at=_now()),
        quality=ProfileQuality(
            has_name=False, has_category=False, has_offerings=False,
            has_audience=False, has_value_propositions=False, has_tone=False,
            has_contact=False, has_visual=False,
            fields_extracted=0, fields_inferred=0, fields_missing=0,
            ready_for_strategy=False,
        ),
        name=_field("Cafe X", page=home),
        category=_field(BusinessCategory.CAFE, page=home),
        offerings=[
            Offering(name="Espresso", evidence=[_ev(home)], confidence=Confidence.MEDIUM),
            Offering(name="Latte", evidence=[_ev(home)], confidence=Confidence.MEDIUM),
            Offering(name="Drip", evidence=[_ev(home)], confidence=Confidence.MEDIUM),
        ],
        audience_type=_field(AudienceType.B2C, page=home),
        value_propositions=[
            _field("Specialty coffee", page=home),
            _field("Hand-roasted", page=home),
        ],
        tone_of_voice=_field(ToneOfVoice.FRIENDLY, page=home),
        description=_field("A specialty coffee bar.", page=home),
        trust_signals=[_field("Award-winning", page=home)],
        contact_channels=ContactChannels(emails=["hi@x.com"]),
        visual=VisualIdentitySummary(primary_logo=_good_logo()),
    )
    p.quality = compute_quality(p)
    return p


# ---------------------------------------------------------------------
# Adapter: scraper-side → business_profile-side
# ---------------------------------------------------------------------

def test_diagnostics_adapter_converts_field_for_field():
    """Manifest carries the scraper-side class; readiness wants the
    business-profile-side class. The adapter must map fields losslessly
    (except sitemap_urls_found, which the readiness layer doesn't need)."""
    from scraper.schemas import ScrapeManifest, ScrapeMeta, RobotsRecord
    from scraper.schemas import ReadinessReport as ScraperReadiness

    manifest = ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url="https://x.com/", normalized_url="https://x.com/",
            scraped_at=_now(),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=ScraperReadiness(
            has_homepage=True, has_internal_pages=False,
            has_contact_signals=False, has_visual_signals=False,
            has_cta_candidates=False, has_metadata=False,
            ready_for_extraction=False,
        ),
        scrape_diagnostics=ScraperDiagnostics(
            pages_discovered=8, pages_scraped=5,
            pages_with_text_blocks=4, pages_failed=1,
            sitemap_used=True, sitemap_urls_found=42,
            js_rendering_used=True,
        ),
    )
    adapted = _diagnostics_from_manifest(manifest)
    assert adapted is not None
    assert adapted.pages_discovered == 8
    assert adapted.pages_scraped == 5
    assert adapted.pages_with_text_blocks == 4
    assert adapted.pages_failed == 1
    assert adapted.sitemap_used is True
    assert adapted.js_rendering_used is True
    # The readiness-side class deliberately does NOT carry sitemap_urls_found
    assert not hasattr(adapted, "sitemap_urls_found")


def test_diagnostics_adapter_returns_none_for_legacy_manifest():
    """Manifests written before PR-1 have no scrape_diagnostics field
    (defaults to None). The adapter must tolerate this."""
    from scraper.schemas import ScrapeManifest, ScrapeMeta, RobotsRecord
    from scraper.schemas import ReadinessReport as ScraperReadiness

    legacy_manifest = ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url="https://x.com/", normalized_url="https://x.com/",
            scraped_at=_now(),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=ScraperReadiness(
            has_homepage=True, has_internal_pages=False,
            has_contact_signals=False, has_visual_signals=False,
            has_cta_candidates=False, has_metadata=False,
            ready_for_extraction=False,
        ),
        # scrape_diagnostics omitted entirely
    )
    assert _diagnostics_from_manifest(legacy_manifest) is None


# ---------------------------------------------------------------------
# Gate behavior with the new diagnostics
# ---------------------------------------------------------------------

def test_single_page_evidence_blocks_swot_when_diagnostics_say_more_pages():
    """When the manifest's diagnostics confirm the scraper SAW more
    pages, single-page-evidence in the profile must hard-block SWOT."""
    p = _build_full_profile_single_page()
    from business_profile.schemas import ScrapeDiagnostics as ProfileDiag
    diag = ProfileDiag(
        pages_discovered=8, pages_scraped=1, pages_with_text_blocks=1,
        pages_failed=2, sitemap_used=True, js_rendering_used=True,
    )
    r = compute_readiness(p, scrape_diagnostics=diag)
    assert "single_page_evidence" in r.swot_blockers
    assert r.ready_for_swot is False


def test_single_page_evidence_only_warns_when_no_other_pages_known():
    """Mirror case: diagnostics confirm only 1 page existed → not a block."""
    p = _build_full_profile_single_page()
    from business_profile.schemas import ScrapeDiagnostics as ProfileDiag
    diag = ProfileDiag(
        pages_discovered=1, pages_scraped=1, pages_with_text_blocks=1,
        sitemap_used=False, js_rendering_used=True,
    )
    r = compute_readiness(p, scrape_diagnostics=diag)
    assert "single_page_evidence" not in r.swot_blockers


def test_diagnostics_pages_discovered_propagates_to_report():
    """The numbers we get out of the readiness report should reflect
    the diagnostics input — this is what the frontend will render."""
    p = _build_full_profile_single_page()
    from business_profile.schemas import ScrapeDiagnostics as ProfileDiag
    diag = ProfileDiag(
        pages_discovered=12, pages_scraped=7,
        pages_with_text_blocks=6, pages_failed=2,
        sitemap_used=True, js_rendering_used=True,
    )
    r = compute_readiness(p, scrape_diagnostics=diag)
    assert r.pages_discovered == 12
    assert r.pages_scraped == 7


# ---------------------------------------------------------------------
# build_profile_no_llm now attaches readiness (PR-1 wiring)
# ---------------------------------------------------------------------

def test_build_profile_no_llm_attaches_readiness():
    """Before PR-1, the no-LLM path did not attach readiness. PR-1
    aligned both paths so the API consumer always sees `readiness`."""
    from business_profile.build import build_profile_no_llm
    from scraper.schemas import (
        ScrapeManifest, ScrapeMeta, RobotsRecord, PageRecord, PageType,
        PageTier, SiteMetadata,
    )
    from scraper.schemas import ReadinessReport as ScraperReadiness

    manifest = ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url="https://x.com/", normalized_url="https://x.com/",
            scraped_at=_now(), pages_attempted=1, pages_succeeded=1,
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=ScraperReadiness(
            has_homepage=True, has_internal_pages=False,
            has_contact_signals=False, has_visual_signals=False,
            has_cta_candidates=False, has_metadata=False,
            ready_for_extraction=True,
        ),
        pages=[PageRecord(
            url="https://x.com/", final_url="https://x.com/",
            http_status=200, fetched_at=_now(), fetch_duration_ms=100,
            page_type=PageType.HOMEPAGE, tier=PageTier.HIGH,
            viewport_width=1366, viewport_height=800,
        )],
        site_metadata=SiteMetadata(),
        scrape_diagnostics=ScraperDiagnostics(
            pages_discovered=1, pages_scraped=1, pages_with_text_blocks=0,
            sitemap_used=False, js_rendering_used=True,
        ),
    )
    profile = build_profile_no_llm(manifest)
    # Must now carry a readiness report (was None before PR-1)
    assert profile.readiness is not None
    # And the manifest diagnostics should have reached it
    assert profile.readiness.pages_discovered == 1
    assert profile.readiness.pages_scraped == 1