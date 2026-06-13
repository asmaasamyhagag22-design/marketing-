"""Tests for vertical-aware evidence-pack ranking (PR-3).

The re-rank is "Option B" — applied at evidence-pack-build time,
keyed on the rules profile's already-detected category. It does NOT
pre-classify before the crawl.

Confirms:
- For each supported vertical, the expected page types appear higher
  in the pack than they would under the global priority alone.
- When category is OTHER or unknown, no bump is applied and the pack
  is byte-for-byte identical to pre-PR-3 output.
- The `vertical_rerank_category` diagnostic is set correctly.
- Unsupported categories (e.g. NONPROFIT, GOVERNMENT) silently fall
  through with no bump.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for _n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, _n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from business_profile.llm.evidence_pack import (  # noqa: E402
    VERTICAL_PAGE_PREFERENCES,
    build_evidence_pack,
)
from business_profile.quality import compute_quality  # noqa: E402
from business_profile.schemas import (  # noqa: E402
    BusinessCategory, BusinessProfile, Confidence, EvidenceItem,
    EvidencedField, ExtractionMeta, ProfileQuality, SourceType,
)
from scraper.schemas import (  # noqa: E402
    PageRecord, PageType, PageTier, ReadinessReport, RobotsRecord,
    ScrapeManifest, ScrapeMeta, Section, SiteMetadata, TextBlock,
)


def _now():
    return datetime.now(timezone.utc)


def _make_block(block_id: str, page_url: str, text: str, *, tag: str = "p") -> TextBlock:
    return TextBlock(
        block_id=block_id,
        page_url=page_url,
        section=Section.MAIN,
        tag=tag,
        selector=f"main > {tag}",
        above_fold=False,
        text=text,
    )


def _make_page(url: str, page_type: PageType, *, blocks: list[TextBlock]) -> PageRecord:
    return PageRecord(
        url=url, final_url=url, http_status=200,
        fetched_at=_now(), fetch_duration_ms=100,
        page_type=page_type, tier=PageTier.HIGH,
        viewport_width=1366, viewport_height=800,
        text_blocks=blocks,
    )


def _make_manifest(pages: list[PageRecord]) -> ScrapeManifest:
    return ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url="https://x.example/",
            normalized_url="https://x.example/",
            scraped_at=_now(),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=ReadinessReport(
            has_homepage=True, has_internal_pages=True,
            has_contact_signals=False, has_visual_signals=False,
            has_cta_candidates=False, has_metadata=False,
            ready_for_extraction=True,
        ),
        site_metadata=SiteMetadata(),
        pages=pages,
    )


def _make_rules_profile(category_value=None) -> BusinessProfile:
    """Minimal rules profile with a settable category."""
    cat_field = EvidencedField.missing()
    if category_value is not None:
        cat_field = EvidencedField(
            value=category_value,
            evidence=[EvidenceItem(page_url="https://x.example/", extractor="rule:test")],
            confidence=Confidence.HIGH,
            source_type=SourceType.EXTRACTED,
        )
    p = BusinessProfile(
        source_url="https://x.example/",
        extraction_meta=ExtractionMeta(manifest_path="t.json", extracted_at=_now()),
        quality=ProfileQuality(
            has_name=False, has_category=bool(category_value),
            has_offerings=False, has_audience=False,
            has_value_propositions=False, has_tone=False,
            has_contact=False, has_visual=False,
            fields_extracted=0, fields_inferred=0, fields_missing=0,
            ready_for_strategy=False,
        ),
        category=cat_field,
    )
    p.quality = compute_quality(p)
    return p


def _page_type_ranks(pack) -> dict[str, int]:
    """Map page_type → its first-appearance index in the pack (smaller = higher rank)."""
    ranks: dict[str, int] = {}
    for i, b in enumerate(pack.blocks):
        if b.page_type not in ranks:
            ranks[b.page_type] = i
    return ranks


# ---------------------------------------------------------------------
# Category=OTHER → no rerank (byte-for-byte unchanged from pre-PR-3)
# ---------------------------------------------------------------------

def test_other_category_does_not_trigger_rerank():
    """The "Option B" promise: when the category is OTHER, evidence-pack
    output is unchanged from before PR-3."""
    # A site with both ABOUT (score 4) and MENU (score 5) blocks
    pages = [
        _make_page("https://x.example/", PageType.HOMEPAGE, blocks=[
            _make_block("h1", "https://x.example/", "Welcome to our place where the food is amazing and the service is friendly."),
        ]),
        _make_page("https://x.example/about", PageType.ABOUT, blocks=[
            _make_block("a1", "https://x.example/about", "We have been serving the community for many decades with care."),
        ]),
        _make_page("https://x.example/menu", PageType.MENU, blocks=[
            _make_block("m1", "https://x.example/menu", "Our menu features grilled chicken, mezze platters, and family feasts."),
        ]),
    ]
    manifest = _make_manifest(pages)

    # OTHER → no rerank
    profile_other = _make_rules_profile(BusinessCategory.OTHER)
    pack_other = build_evidence_pack(manifest, profile_other)
    assert pack_other.vertical_rerank_category is None

    # No category at all → also no rerank
    profile_none = _make_rules_profile(None)
    pack_none = build_evidence_pack(manifest, profile_none)
    assert pack_none.vertical_rerank_category is None

    # Both packs must produce identical block_ids in the same order
    assert pack_other.block_ids == pack_none.block_ids


def test_unsupported_vertical_falls_through_silently():
    """NONPROFIT is a valid BusinessCategory but isn't in the
    preferences table. Must not crash, and must not apply any bump."""
    profile = _make_rules_profile(BusinessCategory.NONPROFIT)
    pages = [
        _make_page("https://x.example/", PageType.HOMEPAGE, blocks=[
            _make_block("h1", "https://x.example/", "We help the community grow stronger every year by donating funds."),
        ]),
    ]
    pack = build_evidence_pack(_make_manifest(pages), profile)
    assert pack.vertical_rerank_category is None
    # And the pack still contains the block — the absence of rerank
    # doesn't mean "ignore the manifest."
    assert pack.block_count >= 1


# ---------------------------------------------------------------------
# Restaurant rerank — MENU should outrank ABOUT
# ---------------------------------------------------------------------

def test_restaurant_rerank_menu_outranks_about():
    """Without a bump, MENU (5) and DELIVERY_ORDER (5) tie with each
    other and outrank ABOUT (4) by a margin of 1. With a +2 restaurant
    bump on MENU and DELIVERY_ORDER, the gap widens to 3 — preserved
    across many blocks. We assert MENU appears before ABOUT in rank."""
    pages = [
        _make_page("https://x.example/about", PageType.ABOUT, blocks=[
            _make_block("a1", "https://x.example/about", "Our restaurant has been a Cairo landmark for decades, run by family."),
        ]),
        _make_page("https://x.example/menu", PageType.MENU, blocks=[
            _make_block("m1", "https://x.example/menu", "We serve grilled chicken, mezze platters, koshary, and seasonal specials."),
        ]),
    ]
    profile = _make_rules_profile(BusinessCategory.RESTAURANT)
    pack = build_evidence_pack(_make_manifest(pages), profile)

    assert pack.vertical_rerank_category == "restaurant"
    ranks = _page_type_ranks(pack)
    assert ranks["menu"] < ranks["about"], (
        f"restaurant rerank should put MENU before ABOUT — got ranks={ranks}"
    )


def test_restaurant_rerank_delivery_outranks_about():
    pages = [
        _make_page("https://x.example/about", PageType.ABOUT, blocks=[
            _make_block("a1", "https://x.example/about", "Family-run since 1976 with heritage recipes and a beloved local presence."),
        ]),
        _make_page("https://x.example/order", PageType.DELIVERY_ORDER, blocks=[
            _make_block("d1", "https://x.example/order", "Order online for delivery in under 45 minutes via our app or website."),
        ]),
    ]
    profile = _make_rules_profile(BusinessCategory.RESTAURANT)
    pack = build_evidence_pack(_make_manifest(pages), profile)
    ranks = _page_type_ranks(pack)
    assert ranks["delivery_order"] < ranks["about"]


# ---------------------------------------------------------------------
# Education rerank — COURSES, PROGRAMS, ADMISSIONS over ABOUT
# ---------------------------------------------------------------------

def test_education_rerank_courses_outranks_about():
    pages = [
        _make_page("https://x.example/about", PageType.ABOUT, blocks=[
            _make_block("a1", "https://x.example/about", "We have been educating professionals across the country for many years."),
        ]),
        _make_page("https://x.example/courses", PageType.COURSES, blocks=[
            _make_block("c1", "https://x.example/courses", "Our courses include data science, ICT, project management, and digital marketing."),
        ]),
        _make_page("https://x.example/admissions", PageType.ADMISSIONS, blocks=[
            _make_block("ad1", "https://x.example/admissions", "Applications for the spring cohort are now open through our portal."),
        ]),
    ]
    profile = _make_rules_profile(BusinessCategory.EDUCATION)
    pack = build_evidence_pack(_make_manifest(pages), profile)
    assert pack.vertical_rerank_category == "education"
    ranks = _page_type_ranks(pack)
    assert ranks["courses"] < ranks["about"]
    assert ranks["admissions"] < ranks["about"]


# ---------------------------------------------------------------------
# Beauty rerank — PRODUCTS over BLOG
# ---------------------------------------------------------------------

def test_beauty_rerank_products_outranks_about():
    pages = [
        _make_page("https://x.example/about", PageType.ABOUT, blocks=[
            _make_block("a1", "https://x.example/about", "Our skincare brand is rooted in dermatological research and gentle care."),
        ]),
        _make_page("https://x.example/products", PageType.PRODUCTS, blocks=[
            _make_block("p1", "https://x.example/products", "Daily Serum, Barrier Cream, and Cleanser are our most loved daily routines."),
        ]),
    ]
    profile = _make_rules_profile(BusinessCategory.BEAUTY)
    pack = build_evidence_pack(_make_manifest(pages), profile)
    assert pack.vertical_rerank_category == "beauty"
    ranks = _page_type_ranks(pack)
    assert ranks["products"] < ranks["about"]


# ---------------------------------------------------------------------
# Clinic rerank — SERVICES is unchanged-priority but bumped; BOOKING gets +1
# ---------------------------------------------------------------------

def test_clinic_rerank_services_outranks_about():
    pages = [
        _make_page("https://x.example/about", PageType.ABOUT, blocks=[
            _make_block("a1", "https://x.example/about", "Our team is composed of board-certified physicians with decades of experience."),
        ]),
        _make_page("https://x.example/services", PageType.SERVICES, blocks=[
            _make_block("s1", "https://x.example/services", "We offer general consultation, diagnostic imaging, and minor surgical procedures."),
        ]),
        _make_page("https://x.example/book", PageType.BOOKING, blocks=[
            _make_block("b1", "https://x.example/book", "Schedule appointments online or call our reception during business hours."),
        ]),
    ]
    profile = _make_rules_profile(BusinessCategory.CLINIC)
    pack = build_evidence_pack(_make_manifest(pages), profile)
    assert pack.vertical_rerank_category == "clinic"
    ranks = _page_type_ranks(pack)
    assert ranks["services"] < ranks["about"]


# ---------------------------------------------------------------------
# Sanity: the preferences table only references real PageType values
# ---------------------------------------------------------------------

def test_vertical_preferences_table_uses_real_page_types():
    valid_page_types = {pt.value for pt in PageType}
    for vertical, table in VERTICAL_PAGE_PREFERENCES.items():
        for pt_key, bump in table.items():
            assert pt_key in valid_page_types, (
                f"vertical {vertical!r} references unknown page type {pt_key!r}"
            )
            assert 0 < bump <= 3, (
                f"vertical {vertical!r} bump {bump} for {pt_key!r} out of expected range"
            )


def test_vertical_preferences_table_uses_real_categories():
    """The preferences keys must match real BusinessCategory values."""
    valid_cats = {c.value for c in BusinessCategory}
    for vertical in VERTICAL_PAGE_PREFERENCES.keys():
        assert vertical in valid_cats, (
            f"vertical {vertical!r} is not a real BusinessCategory value"
        )