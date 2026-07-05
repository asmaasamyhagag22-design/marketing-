"""Tests for the evidence validator.

Covers the rejection codes the validator emits, the field-level
policy that drops scalar values when evidence is invalid, and the
list-item policy that drops items individually.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

# Stub playwright
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
    BoundingBox, LanguageEntry, PageRecord, PageTier, PageType,
    ReadinessReport, RobotsRecord, Section, ScrapeManifest, ScrapeMeta,
    SiteMetadata, TextBlock,
)

from business_profile.llm.caller import MockCaller
from business_profile.llm.evidence_pack import build_evidence_pack
from business_profile.llm.extractor import (
    GroupResult, LLMExtractionResult, run_llm_extraction,
)
from business_profile.llm.responses import (
    IdentityResponse, OfferingItem, OfferingsResponse,
    PositioningResponse, StringListItem, TrustResponse,
)
from business_profile.llm.validator import (
    MAX_QUOTE_LEN,
    RejectionCode,
    _build_lookup,
    _normalize,
    _validate_evidence_item,
    validate_llm_extraction,
)
from business_profile.schemas import (
    AudienceType, BusinessCategory, BusinessProfile, Confidence,
    ExtractionMeta, LLMEvidenceRef, PricingPosture, ProfileQuality,
    ToneOfVoice,
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _block(bid: str, page_url: str, tag: str, text: str,
           section: Section = Section.MAIN, above_fold: bool = False) -> TextBlock:
    return TextBlock(
        block_id=bid, page_url=page_url, tag=tag, text=text, section=section,
        selector=f"{tag}#{bid}",
        bbox=BoundingBox(x=10, y=100, width=200, height=20),
        above_fold=above_fold,
    )


def _pack_with_blocks():
    """Pack with 3 distinct blocks the LLM might cite from."""
    home = "https://x.com/"
    about = "https://x.com/about/"
    m = ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url=home, normalized_url=home, final_url=home, scraped_at=_now(),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=ReadinessReport(
            has_homepage=True, has_internal_pages=True,
            has_contact_signals=False, has_visual_signals=False,
            has_cta_candidates=False, has_metadata=False,
            ready_for_extraction=True,
        ),
        languages=[LanguageEntry(code="en", proportion=1.0)],
        pages=[
            PageRecord(
                url=home, final_url=home, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.HOMEPAGE, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("home_h1_0001", home, "h1",
                           "Premium Foot Care in Cairo", above_fold=True),
                    _block("home_p_0002", home, "p",
                           "Our consultations start from EGP 500."),
                ],
            ),
            PageRecord(
                url=about, final_url=about, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.ABOUT, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("about_p_0001", about, "p",
                           "Founded in 2010, we serve patients across Cairo and Giza."),
                ],
            ),
        ],
        site_metadata=SiteMetadata(),
    )
    profile = BusinessProfile(
        source_url=home,
        extraction_meta=ExtractionMeta(manifest_path="t", extracted_at=_now()),
        quality=ProfileQuality(
            has_name=False, has_category=False, has_offerings=False,
            has_audience=False, has_value_propositions=False, has_tone=False,
            has_contact=False, has_visual=False,
            fields_extracted=0, fields_inferred=0, fields_missing=20,
            ready_for_strategy=False,
        ),
    )
    return build_evidence_pack(m, profile)


def _wrap_in_result(
    identity: IdentityResponse | None = None,
    offerings: OfferingsResponse | None = None,
    positioning: PositioningResponse | None = None,
    trust: TrustResponse | None = None,
) -> LLMExtractionResult:
    """Helper to build an LLMExtractionResult with provided group responses."""
    def _make(group, resp, expected_type):
        if resp is None:
            return GroupResult(group=group, error="not_provided")
        return GroupResult(group=group, response=resp)
    return LLMExtractionResult(
        identity=_make("identity", identity, IdentityResponse),
        offerings=_make("offerings", offerings, OfferingsResponse),
        positioning=_make("positioning", positioning, PositioningResponse),
        trust=_make("trust", trust, TrustResponse),
    )


# ---------------------------------------------------------------------
# Normalize helper
# ---------------------------------------------------------------------

def test_normalize_collapses_whitespace_and_lowercases():
    assert _normalize("  Hello\n  WORLD  ") == "hello world"
    assert _normalize("") == ""
    assert _normalize(None) == ""


def test_normalize_folds_quote_glyphs():
    # The pack shows the LLM `"`->`'`; the validator must fold quotes so a quote of a
    # double-quote (or a smart quote) still matches the original block.
    assert _normalize('We are the "best" clinic') == "we are the 'best' clinic"
    assert _normalize("“smart” ‘quotes’") == "'smart' 'quotes'"


def test_other_unique_insights_validated_and_grounded():
    # The catch-all field is grounded like everything else: a cited+verbatim insight is
    # kept; a hallucinated block_id is dropped.
    pack = _pack_with_blocks()
    pos = PositioningResponse(other_unique_insights=[
        StringListItem(value="Founded in 2010", evidence=[
            LLMEvidenceRef(block_id="about_p_0001", quote="Founded in 2010")]),
        StringListItem(value="totally invented edge", evidence=[
            LLMEvidenceRef(block_id="nope_9999", quote="invented")]),   # hallucinated
    ])
    payload = validate_llm_extraction(_wrap_in_result(positioning=pos), pack)
    kept = [i.value for i in payload.positioning.other_unique_insights]
    assert kept == ["Founded in 2010"]


# ---------------------------------------------------------------------
# Per-item validation: rejection codes
# ---------------------------------------------------------------------

def test_null_block_id_rejected():
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    # Pydantic forbids None for non-Optional fields; LLM might send "" or
    # an explicit None via parse. Construct via dict to bypass type hint.
    ref = LLMEvidenceRef.model_construct(block_id=None, quote="x")
    item, rej = _validate_evidence_item(ref, lookup)
    assert item is None
    assert rej is not None
    assert rej.code == RejectionCode.NULL_BLOCK_ID


def test_empty_block_id_rejected():
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    ref = LLMEvidenceRef(block_id="   ", quote="Premium Foot Care")
    item, rej = _validate_evidence_item(ref, lookup)
    assert item is None and rej is not None
    assert rej.code == RejectionCode.EMPTY_BLOCK_ID


def test_wrong_block_id_with_real_quote_is_recovered():
    # The LLM cited a block_id that doesn't exist, but the quote IS verbatim in a real
    # block — the evidence is real, just mis-attributed, so it is RECOVERED (block_id
    # corrected) instead of discarded (2026-07-05: a wrong block_id used to throw away
    # recoverable real evidence).
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    ref = LLMEvidenceRef(
        block_id="home_h1_9999",             # doesn't exist in pack
        quote="Premium Foot Care in Cairo",  # but this IS block home_h1_0001's text
    )
    item, rej = _validate_evidence_item(ref, lookup)
    assert rej is None and item is not None
    assert item.block_id == "home_h1_0001"   # corrected to the block that holds the quote
    assert item.quote == "Premium Foot Care in Cairo"


def test_wrong_block_id_with_absent_quote_is_rejected():
    # Wrong block_id AND the quote is nowhere in the pack -> genuinely unrecoverable.
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    ref = LLMEvidenceRef(block_id="home_h1_9999", quote="a claim no block ever made")
    item, rej = _validate_evidence_item(ref, lookup)
    assert item is None and rej is not None
    assert rej.code == RejectionCode.HALLUCINATED_BLOCK_ID


def test_empty_quote_rejected():
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    ref = LLMEvidenceRef(block_id="home_h1_0001", quote="   ")
    item, rej = _validate_evidence_item(ref, lookup)
    assert item is None and rej is not None
    assert rej.code == RejectionCode.EMPTY_QUOTE


def test_quote_not_in_block_rejected():
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    ref = LLMEvidenceRef(
        block_id="home_h1_0001",
        quote="something the page never said",
    )
    item, rej = _validate_evidence_item(ref, lookup)
    assert item is None and rej is not None
    assert rej.code == RejectionCode.QUOTE_NOT_IN_BLOCK


def test_quote_paraphrase_rejected():
    """The LLM paraphrasing is a quote rejection, even when 'close enough'."""
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    # block text is "Premium Foot Care in Cairo"
    ref = LLMEvidenceRef(
        block_id="home_h1_0001",
        quote="Premium Footcare in Cairo",  # missing space → not a substring
    )
    item, rej = _validate_evidence_item(ref, lookup)
    assert item is None and rej is not None
    assert rej.code == RejectionCode.QUOTE_NOT_IN_BLOCK


# ---------------------------------------------------------------------
# Per-item validation: accept paths
# ---------------------------------------------------------------------

def test_valid_quote_accepted_verbatim():
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    ref = LLMEvidenceRef(
        block_id="home_h1_0001",
        quote="Premium Foot Care in Cairo",
    )
    item, rej = _validate_evidence_item(ref, lookup)
    assert rej is None and item is not None
    assert item.block_id == "home_h1_0001"
    assert item.quote == "Premium Foot Care in Cairo"
    assert item.page_url == "https://x.com/"
    assert item.extractor == "llm"


def test_valid_quote_substring_accepted():
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    ref = LLMEvidenceRef(
        block_id="home_h1_0001",
        quote="Foot Care",  # substring of "Premium Foot Care in Cairo"
    )
    item, rej = _validate_evidence_item(ref, lookup)
    assert rej is None and item is not None
    assert item.quote == "Foot Care"


def test_valid_quote_case_insensitive_normalization():
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    ref = LLMEvidenceRef(
        block_id="home_h1_0001",
        quote="premium foot CARE in cairo",  # case differs
    )
    item, rej = _validate_evidence_item(ref, lookup)
    assert rej is None and item is not None


def test_valid_quote_whitespace_normalization():
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    ref = LLMEvidenceRef(
        block_id="home_h1_0001",
        quote="Premium\nFoot   Care\tin Cairo",
    )
    item, rej = _validate_evidence_item(ref, lookup)
    assert rej is None and item is not None


def test_quote_wrapped_in_punctuation_accepted():
    """The LLM sometimes wraps quotes in their own punctuation."""
    pack = _pack_with_blocks()
    lookup = _build_lookup(pack)
    ref = LLMEvidenceRef(
        block_id="home_h1_0001",
        quote='"Premium Foot Care in Cairo".',
    )
    item, rej = _validate_evidence_item(ref, lookup)
    assert rej is None and item is not None
    # We stored the cleaned version
    assert item.quote == "Premium Foot Care in Cairo"


def test_long_quote_truncated_then_matched():
    """If quote > 200 chars, the first 200 chars are tried as the candidate.

    To exercise this, we need a block whose text is longer than 200 chars
    AND a quote whose first 200 chars are a true substring of that block.
    """
    home = "https://x.com/"
    long_block_text = (
        "We are a premium clinic in Cairo offering specialized foot care. "
        "Our services include consultations, treatments, custom orthotics, "
        "diabetic foot care, sports injury rehabilitation, and post-operative "
        "recovery programs. " + ("Detail. " * 30)
    )
    assert len(long_block_text) > 250
    # The LLM emits a 250-char quote whose first 200 chars match the block.
    overlong = long_block_text[:250]
    assert len(overlong) > MAX_QUOTE_LEN

    # Build a pack with this block
    m = ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url=home, normalized_url=home, final_url=home, scraped_at=_now(),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=ReadinessReport(
            has_homepage=True, has_internal_pages=False,
            has_contact_signals=False, has_visual_signals=False,
            has_cta_candidates=False, has_metadata=False,
            ready_for_extraction=True,
        ),
        languages=[LanguageEntry(code="en", proportion=1.0)],
        pages=[PageRecord(
            url=home, final_url=home, http_status=200,
            fetched_at=_now(), fetch_duration_ms=1000,
            page_type=PageType.HOMEPAGE, tier=PageTier.HIGH,
            viewport_width=1366, viewport_height=800,
            text_blocks=[_block("long_p_0001", home, "p", long_block_text)],
        )],
        site_metadata=SiteMetadata(),
    )
    # Skip the pack's 600-char block filter by going around build_evidence_pack
    # — directly compose a minimal pack-like lookup.
    from business_profile.llm.evidence_pack import EvidenceBlock, EvidencePack
    pack = EvidencePack(
        source_url=home,
        languages=["en"],
        blocks=[EvidenceBlock(
            block_id="long_p_0001", page_url=home,
            page_type="homepage", section="main", tag="p",
            above_fold=False, text=long_block_text,
        )],
        block_count=1,
        block_ids=["long_p_0001"],
    )
    lookup = _build_lookup(pack)
    ref = LLMEvidenceRef(block_id="long_p_0001", quote=overlong)
    item, rej = _validate_evidence_item(ref, lookup)
    assert rej is None and item is not None
    assert len(item.quote) <= MAX_QUOTE_LEN


# ---------------------------------------------------------------------
# Identity group: field-level policy
# ---------------------------------------------------------------------

def test_identity_invalid_evidence_drops_value():
    pack = _pack_with_blocks()
    resp = IdentityResponse(
        tagline_value="Premium Foot Care in Cairo",
        tagline_evidence=[LLMEvidenceRef(
            block_id="HALLUCINATED_ID",
            # A GENUINELY invalid quote — not verbatim in ANY block, so it is neither
            # matched nor recoverable and the field is correctly dropped. (A wrong
            # block_id whose quote IS real elsewhere is recovered, not dropped — see
            # test_wrong_block_id_with_real_quote_is_recovered.)
            quote="Award-winning care since 1972",
        )],
        tagline_confidence=Confidence.HIGH,
        description_value=None,
        description_evidence=[],
        description_confidence=Confidence.NONE,
        category_value="clinic",
        category_evidence=[LLMEvidenceRef(
            block_id="home_h1_0001",
            quote="Premium Foot Care",
        )],
        category_confidence=Confidence.HIGH,
    )
    payload = validate_llm_extraction(_wrap_in_result(identity=resp), pack)
    assert payload.identity is not None
    # tagline value dropped because its only evidence was hallucinated
    assert payload.identity.tagline.value is None
    assert payload.identity.tagline.evidence == []
    # category survives because its evidence is real
    assert payload.identity.category.value == BusinessCategory.CLINIC
    assert len(payload.identity.category.evidence) == 1
    # Diagnostics record both the rejection and the field drop
    assert "tagline" in payload.diagnostics.fields_dropped
    assert payload.diagnostics.total_rejections >= 1


def test_identity_valid_field_evidence_promoted():
    pack = _pack_with_blocks()
    resp = IdentityResponse(
        tagline_value="Premium Foot Care in Cairo",
        tagline_evidence=[LLMEvidenceRef(
            block_id="home_h1_0001",
            quote="Premium Foot Care in Cairo",
        )],
        tagline_confidence=Confidence.HIGH,
        description_value="A foot care clinic in Cairo offering consultations.",
        description_evidence=[LLMEvidenceRef(
            block_id="home_h1_0001",
            quote="Premium Foot Care in Cairo",
        )],
        description_confidence=Confidence.MEDIUM,
        category_value="clinic",
        category_evidence=[LLMEvidenceRef(
            block_id="home_h1_0001",
            quote="Premium Foot Care",
        )],
        category_confidence=Confidence.HIGH,
    )
    payload = validate_llm_extraction(_wrap_in_result(identity=resp), pack)
    assert payload.identity is not None
    assert payload.identity.tagline.value == "Premium Foot Care in Cairo"
    assert payload.identity.tagline.confidence == Confidence.HIGH
    assert payload.identity.tagline.inferred is False
    assert payload.identity.description.value is not None
    assert payload.identity.description.inferred is True
    assert payload.identity.category.value == BusinessCategory.CLINIC
    assert payload.identity.category.inferred is True
    # page_url should be filled in by the validator
    for f in (payload.identity.tagline, payload.identity.description, payload.identity.category):
        for ev in f.evidence:
            assert ev.page_url == "https://x.com/"
            assert ev.extractor == "llm"


def test_identity_invalid_enum_value_drops_field():
    pack = _pack_with_blocks()
    resp = IdentityResponse(
        category_value="banana_business",  # not in enum
        category_evidence=[LLMEvidenceRef(
            block_id="home_h1_0001", quote="Premium Foot Care",
        )],
        category_confidence=Confidence.HIGH,
    )
    payload = validate_llm_extraction(_wrap_in_result(identity=resp), pack)
    assert payload.identity is not None
    assert payload.identity.category.value is None
    assert "category" in payload.diagnostics.fields_dropped


def test_identity_enum_case_insensitive_coercion():
    pack = _pack_with_blocks()
    resp = IdentityResponse(
        category_value="CLINIC",  # uppercase
        category_evidence=[LLMEvidenceRef(
            block_id="home_h1_0001", quote="Premium Foot Care",
        )],
        category_confidence=Confidence.HIGH,
    )
    payload = validate_llm_extraction(_wrap_in_result(identity=resp), pack)
    assert payload.identity.category.value == BusinessCategory.CLINIC


# ---------------------------------------------------------------------
# Offerings group: list-item policy
# ---------------------------------------------------------------------

def test_offerings_list_drops_invalid_items_individually():
    pack = _pack_with_blocks()
    resp = OfferingsResponse(
        offerings=[
            OfferingItem(
                name="Consultation",
                price_text="EGP 500",
                evidence=[LLMEvidenceRef(
                    block_id="home_p_0002",
                    quote="Our consultations start from EGP 500.",
                )],
                confidence=Confidence.HIGH,
            ),
            # This one has a bad block_id — should be dropped
            OfferingItem(
                name="Imaginary service",
                evidence=[LLMEvidenceRef(
                    block_id="FAKE_ID_999",
                    quote="anything",
                )],
                confidence=Confidence.MEDIUM,
            ),
            # This one has a quote mismatch — should be dropped
            OfferingItem(
                name="Another service",
                evidence=[LLMEvidenceRef(
                    block_id="home_h1_0001",
                    quote="text that is not present anywhere",
                )],
                confidence=Confidence.LOW,
            ),
        ],
        pricing_posture_value="mid",
        pricing_posture_evidence=[LLMEvidenceRef(
            block_id="home_p_0002",
            quote="EGP 500",
        )],
        pricing_posture_confidence=Confidence.MEDIUM,
    )
    payload = validate_llm_extraction(_wrap_in_result(offerings=resp), pack)
    assert payload.offerings is not None
    # Only one valid offering survives
    assert len(payload.offerings.offerings) == 1
    assert payload.offerings.offerings[0].name == "Consultation"
    assert payload.offerings.offerings[0].price_text == "EGP 500"
    # Pricing posture survives
    assert payload.offerings.pricing_posture.value == PricingPosture.MID
    # Diagnostics records the drop count
    assert payload.diagnostics.items_dropped.get("offerings") == 2


def test_offerings_all_invalid_results_in_empty_list():
    pack = _pack_with_blocks()
    resp = OfferingsResponse(
        offerings=[
            OfferingItem(
                name="X", evidence=[LLMEvidenceRef(block_id="FAKE", quote="x")],
            ),
        ],
        pricing_posture_value=None,
    )
    payload = validate_llm_extraction(_wrap_in_result(offerings=resp), pack)
    assert payload.offerings is not None
    assert payload.offerings.offerings == []
    assert payload.offerings.pricing_posture.value is None


def test_offering_with_empty_name_dropped():
    pack = _pack_with_blocks()
    resp = OfferingsResponse(
        offerings=[
            OfferingItem(
                name="   ",
                evidence=[LLMEvidenceRef(
                    block_id="home_p_0002",
                    quote="EGP 500",
                )],
            ),
        ],
    )
    payload = validate_llm_extraction(_wrap_in_result(offerings=resp), pack)
    assert payload.offerings.offerings == []
    assert payload.diagnostics.items_dropped.get("offerings") == 1


# ---------------------------------------------------------------------
# Positioning group: enums + lists together
# ---------------------------------------------------------------------

def test_positioning_full_validation():
    pack = _pack_with_blocks()
    resp = PositioningResponse(
        audience_type_value="B2C",
        audience_type_evidence=[LLMEvidenceRef(
            block_id="home_p_0002",
            quote="Our consultations",
        )],
        audience_type_confidence=Confidence.MEDIUM,
        audience_signals=[
            StringListItem(
                value="individuals seeking foot care",
                evidence=[LLMEvidenceRef(
                    block_id="home_h1_0001", quote="Foot Care",
                )],
            ),
            # This one is bad
            StringListItem(
                value="enterprise IT teams",
                evidence=[LLMEvidenceRef(
                    block_id="HALLUCINATED",
                    quote="anything",
                )],
            ),
        ],
        value_propositions=[
            StringListItem(
                value="Premium positioning",
                evidence=[LLMEvidenceRef(
                    block_id="home_h1_0001", quote="Premium",
                )],
            ),
        ],
        tone_of_voice_value="professional",
        tone_of_voice_evidence=[LLMEvidenceRef(
            block_id="home_h1_0001",
            quote="Premium Foot Care in Cairo",
        )],
        tone_of_voice_confidence=Confidence.MEDIUM,
    )
    payload = validate_llm_extraction(_wrap_in_result(positioning=resp), pack)
    assert payload.positioning is not None
    assert payload.positioning.audience_type.value == AudienceType.B2C
    assert payload.positioning.tone_of_voice.value == ToneOfVoice.PROFESSIONAL
    # The good signal kept, the bad one dropped
    assert len(payload.positioning.audience_signals) == 1
    assert payload.positioning.audience_signals[0].value == "individuals seeking foot care"
    assert payload.positioning.value_propositions[0].value == "Premium positioning"
    assert payload.diagnostics.items_dropped.get("audience_signals") == 1


# ---------------------------------------------------------------------
# Trust group
# ---------------------------------------------------------------------

def test_trust_group_validation():
    pack = _pack_with_blocks()
    resp = TrustResponse(
        trust_signals=[
            StringListItem(
                value="Founded in 2010",
                evidence=[LLMEvidenceRef(
                    block_id="about_p_0001",
                    quote="Founded in 2010",
                )],
            ),
        ],
        service_areas=[
            StringListItem(
                value="Cairo",
                evidence=[LLMEvidenceRef(
                    block_id="about_p_0001",
                    quote="Cairo and Giza",
                )],
            ),
            StringListItem(
                value="Giza",
                evidence=[LLMEvidenceRef(
                    block_id="about_p_0001",
                    quote="Giza",
                )],
            ),
            # Bad
            StringListItem(
                value="London",
                evidence=[LLMEvidenceRef(
                    block_id="about_p_0001",
                    quote="London",  # not in block
                )],
            ),
        ],
    )
    payload = validate_llm_extraction(_wrap_in_result(trust=resp), pack)
    assert payload.trust is not None
    assert len(payload.trust.trust_signals) == 1
    assert payload.trust.trust_signals[0].value == "Founded in 2010"
    assert len(payload.trust.service_areas) == 2
    area_values = {s.value for s in payload.trust.service_areas}
    assert area_values == {"Cairo", "Giza"}


# ---------------------------------------------------------------------
# End-to-end: full validate pass
# ---------------------------------------------------------------------

def test_full_validation_preserves_evidence_chain_and_page_url():
    """Sanity check: after validation, every accepted EvidenceItem
    has block_id (from LLM), quote (from LLM), page_url (from pack),
    extractor='llm' (added by validator)."""
    pack = _pack_with_blocks()
    resp_identity = IdentityResponse(
        tagline_value="Premium Foot Care in Cairo",
        tagline_evidence=[LLMEvidenceRef(
            block_id="home_h1_0001",
            quote="Premium Foot Care in Cairo",
        )],
        tagline_confidence=Confidence.HIGH,
    )
    payload = validate_llm_extraction(
        _wrap_in_result(identity=resp_identity), pack,
    )
    ev = payload.identity.tagline.evidence[0]
    assert ev.block_id == "home_h1_0001"
    assert ev.quote == "Premium Foot Care in Cairo"
    assert ev.page_url == "https://x.com/"  # filled from pack
    assert ev.extractor == "llm"


def test_failed_group_passes_through_as_none():
    """If the extractor failed for a group, the validator skips it cleanly."""
    pack = _pack_with_blocks()
    # offerings group failed at the extractor stage
    result = LLMExtractionResult(
        identity=GroupResult(
            group="identity",
            response=IdentityResponse(
                tagline_value="X",
                tagline_evidence=[LLMEvidenceRef(
                    block_id="home_h1_0001", quote="Premium Foot Care",
                )],
                tagline_confidence=Confidence.HIGH,
            ),
        ),
        offerings=GroupResult(group="offerings", error="api_error"),
        positioning=GroupResult(group="positioning", error="api_error"),
        trust=GroupResult(group="trust", error="api_error"),
    )
    payload = validate_llm_extraction(result, pack)
    assert payload.identity is not None
    assert payload.offerings is None
    assert payload.positioning is None
    assert payload.trust is None


def test_diagnostics_records_each_rejection_per_group():
    pack = _pack_with_blocks()
    resp = IdentityResponse(
        tagline_value="X",
        tagline_evidence=[
            LLMEvidenceRef(block_id="FAKE_1", quote="anything"),
            LLMEvidenceRef(block_id="FAKE_2", quote="anything"),
        ],
        tagline_confidence=Confidence.HIGH,
    )
    payload = validate_llm_extraction(_wrap_in_result(identity=resp), pack)
    rejections = payload.diagnostics.rejections_by_group["identity"]
    assert len(rejections) == 2
    assert all(r.code == RejectionCode.HALLUCINATED_BLOCK_ID for r in rejections)


def test_integration_with_mock_extractor_passes_validation():
    """End-to-end smoke: a clean mock run validates fully with no rejections."""
    from tests.test_llm_extractor import _small_pack, _staged_responses
    pack = _small_pack()
    mock = MockCaller(_staged_responses())
    result = run_llm_extraction(pack, mock)
    payload = validate_llm_extraction(result, pack)

    # All four groups validated
    assert payload.identity is not None
    assert payload.offerings is not None
    assert payload.positioning is not None
    assert payload.trust is not None

    # No rejections — the staged responses use real block_ids
    assert payload.diagnostics.total_rejections == 0

    # Values preserved
    assert payload.identity.tagline.value == "Premium Foot Care in Cairo"
    assert payload.identity.category.value == BusinessCategory.CLINIC
    assert payload.offerings.pricing_posture.value == PricingPosture.MID
    assert payload.positioning.audience_type.value == AudienceType.B2C
    assert payload.positioning.tone_of_voice.value == ToneOfVoice.PROFESSIONAL
    assert payload.trust.service_areas[0].value == "Cairo"
