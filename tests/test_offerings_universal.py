"""Universal offerings extraction tests (v0.2-b1).

Synthetic manifests + staged LLM responses verify the offerings
pipeline produces non-empty results for each supported business
category — including the broader-inference cases for restaurants
(cuisine type, dining experience) where exact menu items aren't
exposed in the scrape.

Failure paths are also covered:
- LLM returns empty list → offerings_extraction_note set
- Validator drops all candidates → distinct note
- Blacklisted unsubstantiated claim → rejected
- LLM skipped → distinct note
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

# Stub playwright BEFORE importing scraper
_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from scraper.schemas import (  # noqa: E402
    BoundingBox, ColorEntry, ContactInfo, EmailRecord, LanguageEntry,
    LinkInventory, LogoRecord, PageRecord, PageTier, PageType,
    PhoneRecord, ReadinessReport, RobotsRecord, ScrapeManifest,
    ScrapeMeta, Section, SiteMetadata, TextBlock, VisualIdentity,
)

from business_profile.llm.caller import MockCaller  # noqa: E402
from business_profile.llm.evidence_pack import build_evidence_pack  # noqa: E402
from business_profile.llm.extractor import run_llm_extraction  # noqa: E402
from business_profile.llm.responses import (  # noqa: E402
    IdentityResponse,
    OfferingItem,
    OfferingsResponse,
    PositioningResponse,
    StringListItem,
    TrustResponse,
)
from business_profile.llm.validator import validate_llm_extraction  # noqa: E402
from business_profile.merger import merge_profile  # noqa: E402
from business_profile.rules.orchestrator import apply_rules  # noqa: E402
from business_profile.schemas import (  # noqa: E402
    BusinessCategory,
    Confidence,
    LLMEvidenceRef,
)


# ---------------------------------------------------------------------
# Fixture builders — one per business type
# ---------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _block(
    bid: str, page_url: str, tag: str, text: str,
    section: Section = Section.MAIN, above_fold: bool = False,
) -> TextBlock:
    return TextBlock(
        block_id=bid, page_url=page_url, tag=tag, text=text, section=section,
        selector=f"{tag}#{bid}",
        bbox=BoundingBox(x=10, y=100, width=200, height=20),
        above_fold=above_fold, is_link=False, href=None,
    )


def _base_manifest_skeleton(
    home_url: str, pages: list[PageRecord],
    *,
    site_meta: SiteMetadata,
    visual: VisualIdentity | None = None,
    contact: ContactInfo | None = None,
) -> ScrapeManifest:
    return ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url=home_url, normalized_url=home_url, final_url=home_url,
            scraped_at=_now(), duration_ms=15000,
            pages_attempted=len(pages), pages_succeeded=len(pages),
        ),
        robots=RobotsRecord(checked=True, allowed=True,
                            robots_url=home_url + "robots.txt"),
        readiness=ReadinessReport(
            has_homepage=True, has_internal_pages=len(pages) > 1,
            has_contact_signals=True, has_visual_signals=True,
            has_cta_candidates=True, has_metadata=True,
            ready_for_extraction=True,
        ),
        languages=[LanguageEntry(code="en", proportion=1.0)],
        pages=pages,
        site_metadata=site_meta,
        visual=visual or VisualIdentity(
            color_palette=[
                ColorEntry(hex="#0a3d62", dominance=0.5),
                ColorEntry(hex="#ffffff", dominance=0.5),
            ],
            primary_button_color="#0a3d62",
            fonts={"body": "Inter", "headings": "Poppins", "buttons": "Inter"},
            logo=LogoRecord(src=home_url + "logo.svg", alt="Logo",
                            page_url=home_url),
        ),
        contact=contact or ContactInfo(
            phones=[PhoneRecord(
                e164="+201001234567", raw="+20 100 123 4567",
                evidence_block_id=None, page_url=home_url,
            )],
            emails=[EmailRecord(
                address="info@example.com",
                evidence_block_id=None, page_url=home_url,
            )],
        ),
        links=LinkInventory(),
    )


# --- Restaurant fixture ---

def _restaurant_manifest() -> ScrapeManifest:
    home = "https://elkbabgi-test.example/"
    menu = home + "menu/"
    return _base_manifest_skeleton(
        home,
        site_meta=SiteMetadata(
            title="El Kababgy - Authentic Egyptian Cuisine",
            og_site_name="El Kababgy",
            schema_org=[],
            html_lang="en",
        ),
        pages=[
            PageRecord(
                url=home, final_url=home, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.HOMEPAGE, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("home_h1", home, "h1",
                           "Authentic Egyptian Cuisine since 1992",
                           above_fold=True),
                    _block("home_p1", home, "p",
                           "El Kababgy is famous for its grilled meats "
                           "and traditional Eastern dishes."),
                    _block("home_p2", home, "p",
                           "We offer family dining, takeaway, and full "
                           "catering services for events."),
                ],
            ),
            PageRecord(
                url=menu, final_url=menu, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.MENU, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("menu_h1", menu, "h1", "Our Menu"),
                    _block("menu_p1", menu, "p",
                           "Mixed Grill Platter - a selection of kofta, "
                           "kebab, and shish tawook."),
                    _block("menu_p2", menu, "p",
                           "Molokhia with rabbit, a traditional Egyptian "
                           "specialty."),
                ],
            ),
        ],
    )


def _restaurant_staged_responses() -> dict:
    """LLM extracts broad cuisine offerings, not just dish names."""
    return {
        "identity": IdentityResponse(
            tagline_value="Authentic Egyptian Cuisine since 1992",
            tagline_evidence=[LLMEvidenceRef(
                block_id="home_h1",
                quote="Authentic Egyptian Cuisine since 1992",
            )],
            tagline_confidence=Confidence.HIGH,
            description_value="A traditional Egyptian restaurant known "
                              "for grilled meats and Eastern cuisine.",
            description_evidence=[LLMEvidenceRef(
                block_id="home_p1",
                quote="famous for its grilled meats",
            )],
            description_confidence=Confidence.HIGH,
            category_value="restaurant",
            category_evidence=[LLMEvidenceRef(
                block_id="home_h1",
                quote="Egyptian Cuisine",
            )],
            category_confidence=Confidence.HIGH,
        ),
        "offerings": OfferingsResponse(
            offerings=[
                # Broad cuisine offering — the key v0.2-b1 case.
                OfferingItem(
                    name="Egyptian cuisine",
                    short_description="Traditional Egyptian dishes including "
                                      "grilled meats and Eastern food.",
                    evidence=[LLMEvidenceRef(
                        block_id="home_h1",
                        quote="Egyptian Cuisine",
                    )],
                    confidence=Confidence.HIGH,
                ),
                OfferingItem(
                    name="Grilled meats",
                    evidence=[LLMEvidenceRef(
                        block_id="home_p1",
                        quote="grilled meats",
                    )],
                    confidence=Confidence.HIGH,
                ),
                # Dining-experience offering.
                OfferingItem(
                    name="Family dining",
                    evidence=[LLMEvidenceRef(
                        block_id="home_p2",
                        quote="family dining",
                    )],
                    confidence=Confidence.MEDIUM,
                ),
                # Service-mode offering.
                OfferingItem(
                    name="Catering services",
                    short_description="Full catering for events.",
                    evidence=[LLMEvidenceRef(
                        block_id="home_p2",
                        quote="full catering services for events",
                    )],
                    confidence=Confidence.HIGH,
                ),
                # Specific dish from the menu page.
                OfferingItem(
                    name="Mixed Grill Platter",
                    short_description="kofta, kebab, and shish tawook",
                    evidence=[LLMEvidenceRef(
                        block_id="menu_p1",
                        quote="Mixed Grill Platter",
                    )],
                    confidence=Confidence.HIGH,
                ),
            ],
            pricing_posture_value="mid",
            pricing_posture_evidence=[LLMEvidenceRef(
                block_id="home_p2", quote="family dining",
            )],
            pricing_posture_confidence=Confidence.LOW,
        ),
        "positioning": PositioningResponse(
            audience_type_value="B2C",
            audience_type_evidence=[LLMEvidenceRef(
                block_id="home_p2", quote="family dining",
            )],
            audience_type_confidence=Confidence.HIGH,
            audience_signals=[StringListItem(
                value="families looking for traditional Egyptian meals",
                evidence=[LLMEvidenceRef(
                    block_id="home_p2", quote="family dining",
                )],
            )],
            value_propositions=[StringListItem(
                value="authentic traditional cuisine",
                evidence=[LLMEvidenceRef(
                    block_id="home_h1", quote="Authentic",
                )],
            )],
            tone_of_voice_value="friendly",
            tone_of_voice_evidence=[LLMEvidenceRef(
                block_id="home_p2", quote="family dining",
            )],
            tone_of_voice_confidence=Confidence.MEDIUM,
        ),
        "trust": TrustResponse(
            trust_signals=[StringListItem(
                value="since 1992",
                evidence=[LLMEvidenceRef(
                    block_id="home_h1", quote="since 1992",
                )],
            )],
            service_areas=[],
        ),
    }


# --- Education fixture ---

def _education_manifest() -> ScrapeManifest:
    home = "https://nti-test.example/"
    courses = home + "courses/"
    return _base_manifest_skeleton(
        home,
        site_meta=SiteMetadata(
            title="National Training Institute",
            og_site_name="NTI",
            schema_org=[],
            html_lang="en",
        ),
        pages=[
            PageRecord(
                url=home, final_url=home, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.HOMEPAGE, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("home_h1", home, "h1",
                           "National Training Institute",
                           above_fold=True),
                    _block("home_p1", home, "p",
                           "We offer professional training programs "
                           "in technology, business, and engineering."),
                ],
            ),
            PageRecord(
                url=courses, final_url=courses, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.COURSES, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("c_python", courses, "h2",
                           "Python for Data Engineering"),
                    _block("c_ml", courses, "h2", "Machine Learning Diploma"),
                    _block("c_pm", courses, "h2", "Project Management Track"),
                ],
            ),
        ],
    )


def _education_staged_responses() -> dict:
    return {
        "identity": IdentityResponse(
            tagline_value="National Training Institute",
            tagline_evidence=[LLMEvidenceRef(
                block_id="home_h1", quote="National Training Institute",
            )],
            tagline_confidence=Confidence.HIGH,
            description_value="A training institute offering professional "
                              "programs in tech, business, and engineering.",
            description_evidence=[LLMEvidenceRef(
                block_id="home_p1", quote="professional training programs",
            )],
            description_confidence=Confidence.HIGH,
            category_value="education",
            category_evidence=[LLMEvidenceRef(
                block_id="home_h1", quote="Training Institute",
            )],
            category_confidence=Confidence.HIGH,
        ),
        "offerings": OfferingsResponse(
            offerings=[
                OfferingItem(
                    name="Python for Data Engineering",
                    evidence=[LLMEvidenceRef(
                        block_id="c_python",
                        quote="Python for Data Engineering",
                    )],
                    confidence=Confidence.HIGH,
                ),
                OfferingItem(
                    name="Machine Learning Diploma",
                    evidence=[LLMEvidenceRef(
                        block_id="c_ml", quote="Machine Learning Diploma",
                    )],
                    confidence=Confidence.HIGH,
                ),
                OfferingItem(
                    name="Project Management Track",
                    evidence=[LLMEvidenceRef(
                        block_id="c_pm", quote="Project Management Track",
                    )],
                    confidence=Confidence.HIGH,
                ),
            ],
            pricing_posture_value="unknown",
            pricing_posture_evidence=[],
            pricing_posture_confidence=Confidence.NONE,
        ),
        "positioning": PositioningResponse(
            audience_type_value="B2C",
            audience_type_evidence=[LLMEvidenceRef(
                block_id="home_p1", quote="professional training",
            )],
            audience_type_confidence=Confidence.MEDIUM,
            audience_signals=[StringListItem(
                value="professionals seeking technical training",
                evidence=[LLMEvidenceRef(
                    block_id="home_p1", quote="professional training",
                )],
            )],
            value_propositions=[StringListItem(
                value="broad curriculum across technology and business",
                evidence=[LLMEvidenceRef(
                    block_id="home_p1",
                    quote="technology, business, and engineering",
                )],
            )],
            tone_of_voice_value="professional",
            tone_of_voice_evidence=[LLMEvidenceRef(
                block_id="home_p1", quote="professional training",
            )],
            tone_of_voice_confidence=Confidence.HIGH,
        ),
        "trust": TrustResponse(trust_signals=[], service_areas=[]),
    }


# --- Ecommerce fixture ---

def _ecommerce_manifest() -> ScrapeManifest:
    home = "https://ariika-test.example/"
    coll = home + "collections/"
    return _base_manifest_skeleton(
        home,
        site_meta=SiteMetadata(
            title="Ariika - Bean Bags and Sofas",
            og_site_name="Ariika",
            schema_org=[],
            html_lang="en",
        ),
        pages=[
            PageRecord(
                url=home, final_url=home, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.HOMEPAGE, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("home_h1", home, "h1",
                           "Comfort redefined", above_fold=True),
                    _block("home_p1", home, "p",
                           "Bean bags, sofas, and outdoor furniture, "
                           "delivered free across Egypt."),
                ],
            ),
            PageRecord(
                url=coll, final_url=coll, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.PRODUCTS, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("c_bean", coll, "h2", "Bean Bags Collection"),
                    _block("c_sofas", coll, "h2", "Sofas Collection"),
                    _block("c_outdoor", coll, "h2", "Outdoor Collection"),
                ],
            ),
        ],
    )


def _ecommerce_staged_responses() -> dict:
    return {
        "identity": IdentityResponse(
            tagline_value="Comfort redefined",
            tagline_evidence=[LLMEvidenceRef(
                block_id="home_h1", quote="Comfort redefined",
            )],
            tagline_confidence=Confidence.HIGH,
            description_value="An Egyptian furniture brand selling bean "
                              "bags, sofas, and outdoor furniture.",
            description_evidence=[LLMEvidenceRef(
                block_id="home_p1", quote="Bean bags, sofas, and outdoor",
            )],
            description_confidence=Confidence.HIGH,
            category_value="ecommerce",
            category_evidence=[LLMEvidenceRef(
                block_id="home_p1", quote="delivered free across Egypt",
            )],
            category_confidence=Confidence.HIGH,
        ),
        "offerings": OfferingsResponse(
            offerings=[
                OfferingItem(
                    name="Bean Bags Collection",
                    evidence=[LLMEvidenceRef(
                        block_id="c_bean", quote="Bean Bags Collection",
                    )],
                    confidence=Confidence.HIGH,
                ),
                OfferingItem(
                    name="Sofas Collection",
                    evidence=[LLMEvidenceRef(
                        block_id="c_sofas", quote="Sofas Collection",
                    )],
                    confidence=Confidence.HIGH,
                ),
                OfferingItem(
                    name="Outdoor Collection",
                    evidence=[LLMEvidenceRef(
                        block_id="c_outdoor", quote="Outdoor Collection",
                    )],
                    confidence=Confidence.HIGH,
                ),
                OfferingItem(
                    name="Free delivery across Egypt",
                    evidence=[LLMEvidenceRef(
                        block_id="home_p1",
                        quote="delivered free across Egypt",
                    )],
                    confidence=Confidence.HIGH,
                ),
            ],
            pricing_posture_value="mid",
            pricing_posture_evidence=[LLMEvidenceRef(
                block_id="home_h1", quote="Comfort redefined",
            )],
            pricing_posture_confidence=Confidence.LOW,
        ),
        "positioning": PositioningResponse(
            audience_type_value="B2C",
            audience_type_evidence=[LLMEvidenceRef(
                block_id="home_p1", quote="across Egypt",
            )],
            audience_type_confidence=Confidence.MEDIUM,
            audience_signals=[StringListItem(
                value="home and outdoor furniture buyers in Egypt",
                evidence=[LLMEvidenceRef(
                    block_id="home_p1", quote="across Egypt",
                )],
            )],
            value_propositions=[StringListItem(
                value="free delivery nationwide",
                evidence=[LLMEvidenceRef(
                    block_id="home_p1", quote="delivered free across Egypt",
                )],
            )],
            tone_of_voice_value="friendly",
            tone_of_voice_evidence=[LLMEvidenceRef(
                block_id="home_h1", quote="Comfort redefined",
            )],
            tone_of_voice_confidence=Confidence.MEDIUM,
        ),
        "trust": TrustResponse(trust_signals=[], service_areas=[]),
    }


# --- Beauty/skincare fixture ---

def _beauty_manifest() -> ScrapeManifest:
    home = "https://beauty-test.example/"
    products = home + "products/"
    return _base_manifest_skeleton(
        home,
        site_meta=SiteMetadata(
            title="Glow Skincare",
            og_site_name="Glow",
            schema_org=[],
            html_lang="en",
        ),
        pages=[
            PageRecord(
                url=home, final_url=home, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.HOMEPAGE, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("home_h1", home, "h1",
                           "Glow Skincare for everyday radiance",
                           above_fold=True),
                    _block("home_p1", home, "p",
                           "Cleansers, serums, and moisturizers crafted "
                           "for sensitive skin."),
                ],
            ),
            PageRecord(
                url=products, final_url=products, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.PRODUCTS, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("p_cleanser", products, "h2", "Gentle Cleanser"),
                    _block("p_serum", products, "h2", "Hydrating Serum"),
                ],
            ),
        ],
    )


def _beauty_staged_responses() -> dict:
    return {
        "identity": IdentityResponse(
            tagline_value="Glow Skincare for everyday radiance",
            tagline_evidence=[LLMEvidenceRef(
                block_id="home_h1",
                quote="Glow Skincare for everyday radiance",
            )],
            tagline_confidence=Confidence.HIGH,
            description_value="A skincare brand for sensitive skin offering "
                              "cleansers, serums, and moisturizers.",
            description_evidence=[LLMEvidenceRef(
                block_id="home_p1",
                quote="Cleansers, serums, and moisturizers",
            )],
            description_confidence=Confidence.HIGH,
            category_value="beauty",
            category_evidence=[LLMEvidenceRef(
                block_id="home_h1", quote="Skincare",
            )],
            category_confidence=Confidence.HIGH,
        ),
        "offerings": OfferingsResponse(
            offerings=[
                OfferingItem(
                    name="Cleansers",
                    evidence=[LLMEvidenceRef(
                        block_id="home_p1", quote="Cleansers",
                    )],
                    confidence=Confidence.HIGH,
                ),
                OfferingItem(
                    name="Serums",
                    evidence=[LLMEvidenceRef(
                        block_id="home_p1", quote="serums",
                    )],
                    confidence=Confidence.HIGH,
                ),
                OfferingItem(
                    name="Moisturizers",
                    evidence=[LLMEvidenceRef(
                        block_id="home_p1", quote="moisturizers",
                    )],
                    confidence=Confidence.HIGH,
                ),
            ],
            pricing_posture_value="unknown",
            pricing_posture_evidence=[],
            pricing_posture_confidence=Confidence.NONE,
        ),
        "positioning": PositioningResponse(
            audience_type_value="B2C",
            audience_type_evidence=[LLMEvidenceRef(
                block_id="home_p1", quote="sensitive skin",
            )],
            audience_type_confidence=Confidence.HIGH,
            audience_signals=[StringListItem(
                value="people with sensitive skin",
                evidence=[LLMEvidenceRef(
                    block_id="home_p1", quote="sensitive skin",
                )],
            )],
            value_propositions=[StringListItem(
                value="formulations for sensitive skin",
                evidence=[LLMEvidenceRef(
                    block_id="home_p1",
                    quote="crafted for sensitive skin",
                )],
            )],
            tone_of_voice_value="friendly",
            tone_of_voice_evidence=[LLMEvidenceRef(
                block_id="home_h1", quote="everyday radiance",
            )],
            tone_of_voice_confidence=Confidence.MEDIUM,
        ),
        "trust": TrustResponse(trust_signals=[], service_areas=[]),
    }


# ---------------------------------------------------------------------
# Pipeline driver helper
# ---------------------------------------------------------------------

def _run_pipeline(manifest: ScrapeManifest, staged: dict):
    rules_profile = apply_rules(manifest, "test/manifest.json")
    pack = build_evidence_pack(manifest, rules_profile)
    caller = MockCaller(staged, input_tokens=400, output_tokens=150,
                        model="gpt-4o-mini")
    rules_cat = (
        rules_profile.category.value.value
        if rules_profile.category.value is not None
        else None
    )
    llm_result = run_llm_extraction(pack, caller, rules_category=rules_cat)
    payload = validate_llm_extraction(llm_result, pack)
    final = merge_profile(rules_profile, payload, llm_result, expected_llm=True)
    return final, payload, llm_result


# ---------------------------------------------------------------------
# Happy-path tests per category
# ---------------------------------------------------------------------

def test_restaurant_extracts_broad_offerings_not_just_dishes():
    """Restaurant case: cuisine type + dining experience + catering get extracted,
    not just the single named dish."""
    final, _, _ = _run_pipeline(
        _restaurant_manifest(), _restaurant_staged_responses(),
    )
    assert final.category.value == BusinessCategory.RESTAURANT
    names = [o.name for o in final.offerings]
    assert len(names) >= 4, f"expected >=4 offerings, got {names}"
    # Broad cuisine offering must be present
    assert any("egyptian cuisine" in n.lower() for n in names)
    # Dining-experience offering must be present
    assert any("family dining" in n.lower() for n in names)
    # Service-mode offering must be present
    assert any("catering" in n.lower() for n in names)
    # Specific dish must also survive (not just broad ones)
    assert any("mixed grill platter" in n.lower() for n in names)
    # Note must be cleared when offerings are populated
    assert final.offerings_extraction_note is None
    # ready_for_poster must hold for a well-formed restaurant profile
    assert final.quality.ready_for_poster is True


def test_education_extracts_courses_and_programs():
    final, _, _ = _run_pipeline(
        _education_manifest(), _education_staged_responses(),
    )
    assert final.category.value == BusinessCategory.EDUCATION
    names = [o.name for o in final.offerings]
    assert len(names) >= 3
    assert any("python" in n.lower() for n in names)
    assert any("machine learning" in n.lower() for n in names)
    assert any("project management" in n.lower() for n in names)
    # Education profile typically lacks audience-specific contact path,
    # but our fixture has contact so it should be poster-ready.
    assert final.quality.ready_for_poster is True


def test_ecommerce_extracts_collections_and_delivery():
    final, _, _ = _run_pipeline(
        _ecommerce_manifest(), _ecommerce_staged_responses(),
    )
    assert final.category.value == BusinessCategory.ECOMMERCE
    names = [o.name for o in final.offerings]
    assert len(names) >= 3
    # Collection-level offerings (not individual SKUs)
    assert any("bean bags collection" in n.lower() for n in names)
    assert any("sofas collection" in n.lower() for n in names)
    # Service mode (delivery)
    assert any("delivery" in n.lower() for n in names)
    assert final.quality.ready_for_poster is True


def test_beauty_skincare_extracts_categories():
    final, _, _ = _run_pipeline(
        _beauty_manifest(), _beauty_staged_responses(),
    )
    assert final.category.value == BusinessCategory.BEAUTY
    names = [o.name for o in final.offerings]
    assert len(names) >= 3
    assert any("cleanser" in n.lower() for n in names)
    assert any("serum" in n.lower() for n in names)
    assert final.quality.ready_for_poster is True


# ---------------------------------------------------------------------
# Failure path tests (the heart of "no silent success")
# ---------------------------------------------------------------------

def _no_offering_signals_manifest() -> ScrapeManifest:
    """A minimal services-style site with NO restaurant/menu/cuisine signals.

    Used by the Case A failure-path tests, where we want to assert that
    when neither the LLM nor the rule-based extractor can recover any
    offering, the merger sets the correct extraction note.

    The text deliberately avoids every trigger of `_OFFERING_PATTERNS`
    in `business_profile/rules/from_offerings.py` (no "cuisine", "menu",
    "grill", "dishes", "dining", "takeaway", "delivery", "catering",
    "stew", "molokhia", etc.). It also uses page_type=OTHER so the
    restaurant rule extractor short-circuits before any text scan.
    """
    home = "https://emptyco-test.example/"
    return _base_manifest_skeleton(
        home,
        site_meta=SiteMetadata(
            title="EmptyCo - Our Story",
            og_site_name="EmptyCo",
            schema_org=[],
            html_lang="en",
        ),
        pages=[
            PageRecord(
                url=home, final_url=home, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.OTHER, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("home_h1", home, "h1",
                           "Welcome to EmptyCo", above_fold=True),
                    _block("home_p1", home, "p",
                           "We are a small company based in the city."),
                    _block("home_p2", home, "p",
                           "Our team has been working together for a while."),
                ],
            ),
        ],
    )


def _empty_offerings_responses() -> dict:
    """All LLM groups respond, but offerings list is empty."""
    base = _restaurant_staged_responses()
    base["offerings"] = OfferingsResponse(
        offerings=[],
        pricing_posture_value="unknown",
        pricing_posture_evidence=[],
        pricing_posture_confidence=Confidence.NONE,
    )
    return base


def test_empty_offerings_sets_llm_returned_zero_note():
    """Case A — truly empty offerings.

    Uses a fixture with NO food/menu/cuisine/dining/catering text and
    a non-restaurant page type, so neither the LLM nor the rule-based
    fallback can recover anything. The merger must set the correct
    extraction note explaining why offerings is empty.
    """
    final, _, _ = _run_pipeline(
        _no_offering_signals_manifest(), _empty_offerings_responses(),
    )
    assert len(final.offerings) == 0
    assert final.offerings_extraction_note == "llm_returned_zero_offerings"


def test_llm_zero_offerings_with_rule_recovery_keeps_profile_useful():
    """Case B — LLM returned zero, but the restaurant rule extractor recovered.

    This is the campaign-ready behavior we want: when a restaurant
    fixture contains real menu/cuisine text, evidenced offerings should
    be extracted by `rule:restaurant_offering_text` even if the LLM
    returned an empty list. The profile remains campaign-useful, and
    the extraction note is None because there is no failure to explain.
    """
    final, _, _ = _run_pipeline(
        _restaurant_manifest(), _empty_offerings_responses(),
    )
    assert len(final.offerings) > 0, "rule-based extractor should recover offerings"
    # Note must be None: offerings are populated, no failure to report.
    assert final.offerings_extraction_note is None
    # Every recovered offering must come from the rule extractor (not LLM,
    # which returned []) and must carry direct evidence.
    for o in final.offerings:
        assert o.evidence, f"offering {o.name!r} missing evidence"
        assert all(ev.extractor == "rule:restaurant_offering_text" for ev in o.evidence), (
            f"offering {o.name!r} has non-rule extractor: "
            f"{[ev.extractor for ev in o.evidence]}"
        )
    # The profile must remain poster-ready via the recovered offerings.
    assert final.quality.ready_for_poster is True
    assert "no_offer_or_strong_positioning" not in final.quality.poster_blockers


def _all_rejected_offerings_responses() -> dict:
    """LLM returns offerings, but all evidence cites non-existent block_ids."""
    base = _restaurant_staged_responses()
    base["offerings"] = OfferingsResponse(
        offerings=[
            OfferingItem(
                name="Some offering",
                evidence=[LLMEvidenceRef(
                    block_id="DOES_NOT_EXIST", quote="ghost",
                )],
                confidence=Confidence.HIGH,
            ),
            OfferingItem(
                name="Another offering",
                evidence=[LLMEvidenceRef(
                    block_id="ALSO_GHOST", quote="phantom",
                )],
                confidence=Confidence.HIGH,
            ),
        ],
        pricing_posture_value="unknown",
        pricing_posture_evidence=[],
        pricing_posture_confidence=Confidence.NONE,
    )
    return base


def test_all_rejected_sets_validator_drop_note():
    """Case A — LLM returned candidates, all rejected by validator,
    and no rule-based recovery is possible.

    Uses the no-signals fixture so the restaurant rule extractor cannot
    rescue offerings, isolating the validator-drop note path.
    """
    final, _, _ = _run_pipeline(
        _no_offering_signals_manifest(), _all_rejected_offerings_responses(),
    )
    assert len(final.offerings) == 0
    assert (
        final.offerings_extraction_note
        == "all_candidates_rejected_by_validator"
    )


def test_all_rejected_with_rule_recovery_keeps_profile_useful():
    """Case B — LLM candidates were all rejected, but rules still recover.

    The validator dropping every LLM candidate must NOT prevent the
    restaurant rule extractor from contributing offerings. The merger
    keeps the recovered offerings and clears the extraction note.
    """
    final, _, _ = _run_pipeline(
        _restaurant_manifest(), _all_rejected_offerings_responses(),
    )
    assert len(final.offerings) > 0, "rule extractor should recover offerings"
    assert final.offerings_extraction_note is None
    for o in final.offerings:
        assert o.evidence
        assert all(ev.extractor == "rule:restaurant_offering_text" for ev in o.evidence)
    assert final.quality.ready_for_poster is True


# ---------------------------------------------------------------------
# Blacklist enforcement
# ---------------------------------------------------------------------

def _halal_inferred_responses() -> dict:
    """LLM tries to claim 'halal' without the word appearing in any quote."""
    base = _restaurant_staged_responses()
    base["offerings"] = OfferingsResponse(
        offerings=[
            OfferingItem(
                # Bad: 'halal' is in the name but not in the cited quote.
                name="Halal Egyptian cuisine",
                short_description="Traditional dishes.",
                evidence=[LLMEvidenceRef(
                    block_id="home_h1",
                    # quote does NOT contain "halal"
                    quote="Authentic Egyptian Cuisine",
                )],
                confidence=Confidence.HIGH,
            ),
            # Good: should survive (no blacklist token in name)
            OfferingItem(
                name="Egyptian cuisine",
                evidence=[LLMEvidenceRef(
                    block_id="home_h1", quote="Egyptian Cuisine",
                )],
                confidence=Confidence.HIGH,
            ),
        ],
        pricing_posture_value="unknown",
        pricing_posture_evidence=[],
        pricing_posture_confidence=Confidence.NONE,
    )
    return base


def test_blacklist_rejects_unsubstantiated_halal_claim():
    final, payload, _ = _run_pipeline(
        _restaurant_manifest(), _halal_inferred_responses(),
    )
    names = [o.name for o in final.offerings]
    # "halal" was not in any cited quote → must be dropped
    assert not any("halal" in n.lower() for n in names)
    # The clean offering must survive
    assert any("egyptian cuisine" in n.lower() for n in names)
    # Blacklist rejection must be recorded in diagnostics
    assert "offerings" in payload.diagnostics.blacklist_rejections
    assert len(payload.diagnostics.blacklist_rejections["offerings"]) >= 1


def _halal_supported_responses() -> dict:
    """LLM claims 'halal' AND the cited quote literally contains the word."""
    base = _restaurant_staged_responses()
    # Add a block that contains "halal" so the claim is supported.
    home = "https://elkbabgi-test.example/"
    # We need to mutate the manifest too; this fixture overrides via direct
    # quote since the cited block_id home_h1's existing text is "Authentic
    # Egyptian Cuisine since 1992" — no "halal". So we mock a scenario where
    # one cited block does contain the word.
    base["offerings"] = OfferingsResponse(
        offerings=[
            OfferingItem(
                name="Halal cuisine",
                short_description="All meat is halal certified.",
                evidence=[LLMEvidenceRef(
                    # quote contains both "halal" and "certified"
                    block_id="home_p1",
                    quote="halal certified",
                )],
                confidence=Confidence.HIGH,
            ),
        ],
        pricing_posture_value="unknown",
        pricing_posture_evidence=[],
        pricing_posture_confidence=Confidence.NONE,
    )
    return base


def test_blacklist_allows_claim_when_quote_contains_token():
    # Mutate the restaurant manifest so the cited block actually contains
    # "halal certified" — proving the claim is grounded.
    manifest = _restaurant_manifest()
    # Replace home_p1 text to literally contain the blacklist tokens.
    home_page = manifest.pages[0]
    new_blocks = []
    for b in home_page.text_blocks:
        if b.block_id == "home_p1":
            new_blocks.append(TextBlock(
                block_id=b.block_id, page_url=b.page_url, tag=b.tag,
                text="All meat is halal certified by an accredited authority.",
                section=b.section, selector=b.selector, bbox=b.bbox,
                above_fold=b.above_fold, is_link=b.is_link, href=b.href,
            ))
        else:
            new_blocks.append(b)
    manifest.pages[0] = PageRecord(
        url=home_page.url, final_url=home_page.final_url,
        http_status=home_page.http_status, fetched_at=home_page.fetched_at,
        fetch_duration_ms=home_page.fetch_duration_ms,
        page_type=home_page.page_type, tier=home_page.tier,
        viewport_width=home_page.viewport_width,
        viewport_height=home_page.viewport_height,
        text_blocks=new_blocks,
    )

    final, payload, _ = _run_pipeline(manifest, _halal_supported_responses())
    names = [o.name for o in final.offerings]
    # The supported "halal" claim should survive
    assert any("halal" in n.lower() for n in names), (
        f"halal claim was rejected despite being in cited quote. "
        f"blacklist_rejections={payload.diagnostics.blacklist_rejections}"
    )


# ---------------------------------------------------------------------
# Schema version + LLM silent failure
# ---------------------------------------------------------------------

def test_schema_version_is_set():
    final, _, _ = _run_pipeline(
        _restaurant_manifest(), _restaurant_staged_responses(),
    )
    assert final.schema_version == "0.2.0"


def test_skip_llm_path_sets_llm_skipped_note():
    """Case A — rules-only build path on a site with no offering signals.

    `offerings_extraction_note` must be 'llm_skipped' (not
    'llm_returned_zero_offerings').
    """
    from business_profile.build import build_profile_no_llm
    manifest = _no_offering_signals_manifest()
    profile = build_profile_no_llm(manifest)
    assert len(profile.offerings) == 0
    assert profile.offerings_extraction_note == "llm_skipped"
    assert profile.llm_silent_failure is False


def test_skip_llm_path_with_rule_recovery_keeps_profile_useful():
    """Case B — rules-only build path on a restaurant fixture.

    Even with the LLM skipped, the rule-based restaurant offering
    extractor must populate offerings from the menu/cuisine text. The
    profile remains campaign-useful, the LLM-skipped state does NOT
    constitute a silent failure, and the extraction note is None
    because offerings are populated.
    """
    from business_profile.build import build_profile_no_llm
    manifest = _restaurant_manifest()
    profile = build_profile_no_llm(manifest)
    assert len(profile.offerings) > 0, "rule extractor should recover offerings"
    assert profile.offerings_extraction_note is None
    for o in profile.offerings:
        assert o.evidence
        assert all(ev.extractor == "rule:restaurant_offering_text" for ev in o.evidence)
    assert profile.llm_silent_failure is False
    # NOTE: ready_for_poster requires category + brand statement, which the
    # rules-only path does not always produce. We assert the campaign-useful
    # part (offerings exist with real evidence), not the full poster gate.


def test_llm_silent_failure_when_all_groups_error():
    """If skip_llm=false but every LLM group call fails, llm_silent_failure
    must be True and ready_for_poster must be False."""
    manifest = _restaurant_manifest()
    rules_profile = apply_rules(manifest, "test/m.json")
    pack = build_evidence_pack(manifest, rules_profile)
    caller = MockCaller(
        _restaurant_staged_responses(),
        raise_on_group={"identity", "offerings", "positioning", "trust"},
        model="gpt-4o-mini",
    )
    llm_result = run_llm_extraction(pack, caller, rules_category="restaurant")
    payload = validate_llm_extraction(llm_result, pack)
    final = merge_profile(rules_profile, payload, llm_result, expected_llm=True)
    assert final.llm_silent_failure is True
    assert final.quality.ready_for_poster is False
    assert "llm_silent_failure" in final.quality.poster_blockers

def test_boutique_size_check_precedes_departments_rule():
    # R2b (rawafrican: 8 category-level unpriced offerings despite 11 priced product pages
    # in evidence): the DEPARTMENTS-FIRST rule was written for giant marketplaces and was
    # collapsing boutiques. Both store shapes now open with the SIZE CHECK: a boutique
    # catalog (~<=40 products) lists INDIVIDUAL products with verbatim price_text.
    from business_profile.llm.evidence_pack import EvidenceBlock, EvidencePack
    from business_profile.llm.prompts import build_offerings_prompt
    pack = EvidencePack(source_url="https://b.com/", languages=["en"],
                        blocks=[EvidenceBlock(block_id="b1", page_url="https://b.com/",
                                              page_type="homepage", section="main", tag="p",
                                              above_fold=True, text="Hair Oil EGP 250")],
                        block_count=1, block_ids=["b1"])
    for cat in ("ecommerce", None):
        p = build_offerings_prompt(pack, rules_category=cat)
        assert "SIZE CHECK FIRST" in p
        assert p.index("SIZE CHECK FIRST") < p.index("DEPARTMENTS FIRST")
        assert "price_text VERBATIM" in p
