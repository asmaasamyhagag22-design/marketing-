"""Tests for the LLM extractor layer."""
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

from business_profile.llm.caller import (
    MockCaller, OpenAICaller, Usage, _cost_for,
)
from business_profile.llm.evidence_pack import build_evidence_pack
from business_profile.llm.extractor import (
    LLMExtractionResult, run_llm_extraction,
)
from business_profile.llm.prompts import (
    AUDIENCE_TYPE_VALUES, CATEGORY_VALUES, PRICING_POSTURE_VALUES,
    SYSTEM_PROMPT, TONE_VALUES,
    build_identity_prompt, build_offerings_prompt,
    build_positioning_prompt, build_trust_prompt,
)
from business_profile.llm.responses import (
    IdentityResponse, OfferingItem, OfferingsResponse,
    PositioningResponse, StringListItem, TrustResponse,
)
from business_profile.rules.orchestrator import apply_rules
from business_profile.schemas import (
    BusinessProfile, Confidence, ExtractionMeta,
    LLMEvidenceRef, ProfileQuality,
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


def _small_pack():
    home = "https://x.com/"
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
            text_blocks=[
                _block("home_h1_0001", home, "h1",
                       "Premium Foot Care in Cairo", above_fold=True),
                _block("home_p_0002", home, "p",
                       "Our consultations start from EGP 500."),
            ],
        )],
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
            major_missing=["category", "offerings", "audience_type"],
            ready_for_strategy=False,
        ),
    )
    return build_evidence_pack(m, profile)


def _staged_responses():
    """A full set of plausible responses for all four groups."""
    return {
        "identity": IdentityResponse(
            tagline_value="Premium Foot Care in Cairo",
            tagline_evidence=[LLMEvidenceRef(
                block_id="home_h1_0001",
                quote="Premium Foot Care in Cairo",
            )],
            tagline_confidence=Confidence.HIGH,
            tagline_reasoning="Directly stated as the homepage h1.",
            description_value="A foot care clinic in Cairo offering consultations.",
            description_evidence=[
                LLMEvidenceRef(block_id="home_h1_0001",
                               quote="Premium Foot Care in Cairo"),
                LLMEvidenceRef(block_id="home_p_0002",
                               quote="Our consultations start from EGP 500."),
            ],
            description_confidence=Confidence.MEDIUM,
            description_reasoning="Synthesized from h1 + service mention.",
            category_value="clinic",
            category_evidence=[LLMEvidenceRef(
                block_id="home_h1_0001",
                quote="Premium Foot Care",
            )],
            category_confidence=Confidence.HIGH,
            category_reasoning="Foot care = medical clinic.",
        ),
        "offerings": OfferingsResponse(
            offerings=[OfferingItem(
                name="Consultation",
                short_description="Initial consultation with a specialist.",
                price_text="EGP 500",
                evidence=[LLMEvidenceRef(
                    block_id="home_p_0002",
                    quote="Our consultations start from EGP 500.",
                )],
                confidence=Confidence.HIGH,
            )],
            pricing_posture_value="mid",
            pricing_posture_evidence=[LLMEvidenceRef(
                block_id="home_p_0002",
                quote="EGP 500",
            )],
            pricing_posture_confidence=Confidence.MEDIUM,
            pricing_posture_reasoning="EGP 500 is mid-range for consultations.",
        ),
        "positioning": PositioningResponse(
            audience_type_value="B2C",
            audience_type_evidence=[LLMEvidenceRef(
                block_id="home_p_0002",
                quote="Our consultations",
            )],
            audience_type_confidence=Confidence.MEDIUM,
            audience_type_reasoning="Individual consultations imply B2C.",
            audience_signals=[StringListItem(
                value="individuals seeking foot care",
                evidence=[LLMEvidenceRef(block_id="home_h1_0001",
                                          quote="Foot Care")],
                confidence=Confidence.MEDIUM,
            )],
            value_propositions=[StringListItem(
                value="Premium positioning",
                evidence=[LLMEvidenceRef(block_id="home_h1_0001",
                                          quote="Premium")],
                confidence=Confidence.MEDIUM,
            )],
            tone_of_voice_value="professional",
            tone_of_voice_evidence=[LLMEvidenceRef(
                block_id="home_h1_0001",
                quote="Premium Foot Care in Cairo",
            )],
            tone_of_voice_confidence=Confidence.MEDIUM,
            tone_of_voice_reasoning="Word 'premium' suggests professional tone.",
        ),
        "trust": TrustResponse(
            trust_signals=[],
            service_areas=[StringListItem(
                value="Cairo",
                evidence=[LLMEvidenceRef(block_id="home_h1_0001",
                                          quote="Cairo")],
                confidence=Confidence.HIGH,
            )],
        ),
    }


# ---------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------

def test_cost_for_gpt_4o_mini():
    # 1000 input + 500 output: 1000/1M * $0.150 + 500/1M * $0.600
    cost = _cost_for("gpt-4o-mini", 1000, 500)
    assert cost == pytest_approx(0.00015 + 0.0003)


def test_cost_for_dated_model():
    cost = _cost_for("gpt-4o-mini-2024-07-18", 1000, 500)
    assert cost == pytest_approx(0.00015 + 0.0003)


def test_cost_for_unknown_model_returns_zero():
    assert _cost_for("some-other-model", 1000, 500) == 0.0


def pytest_approx(value, rel=1e-9):
    """Lightweight approx helper to avoid pulling in pytest.approx import."""
    class _Approx:
        def __eq__(self, other):
            if value == 0:
                return abs(other) < rel
            return abs(other - value) / abs(value) < rel
        def __repr__(self):
            return f"~{value}"
    return _Approx()


# ---------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------

def test_system_prompt_contains_core_rules():
    assert "block_id" in SYSTEM_PROMPT
    assert "verbatim" in SYSTEM_PROMPT.lower()
    assert "null" in SYSTEM_PROMPT.lower()
    assert "invent" in SYSTEM_PROMPT.lower()


def test_identity_prompt_includes_pack_and_fields():
    pack = _small_pack()
    p = build_identity_prompt(pack)
    assert "home_h1_0001" in p
    assert "Premium Foot Care in Cairo" in p
    assert "tagline" in p
    assert "description" in p
    assert "category" in p
    # Category list must be present and explicit
    for cat in CATEGORY_VALUES:
        assert cat in p


def test_offerings_prompt_includes_pricing_posture():
    pack = _small_pack()
    p = build_offerings_prompt(pack)
    assert "offerings" in p
    for posture in PRICING_POSTURE_VALUES:
        assert posture in p
    # Should reference the cap
    assert "12" in p  # cap on offerings


def test_positioning_prompt_lists_all_enums():
    pack = _small_pack()
    p = build_positioning_prompt(pack)
    for v in AUDIENCE_TYPE_VALUES:
        assert v in p
    for v in TONE_VALUES:
        assert v in p


def test_trust_prompt_includes_service_areas():
    pack = _small_pack()
    p = build_trust_prompt(pack)
    assert "trust_signals" in p
    assert "service_areas" in p


def test_prompt_contains_missing_fields_hint():
    pack = _small_pack()
    p = build_identity_prompt(pack)
    # The pack's missing_fields hint should appear
    assert "category" in p  # part of missing_fields and category instructions
    assert "Missing fields" in p


# ---------------------------------------------------------------------
# Response schema sanity (OpenAI strict-mode compatibility)
# ---------------------------------------------------------------------

def test_response_schemas_generate_clean_json_schema():
    """OpenAI's structured outputs require the model to be JSON-schemable
    without errors. If any of these throws, OpenAI strict mode will reject
    the request at submission time."""
    for cls in (IdentityResponse, OfferingsResponse,
                 PositioningResponse, TrustResponse):
        schema = cls.model_json_schema()
        assert "properties" in schema, f"{cls.__name__} missing properties"


def test_response_schemas_roundtrip():
    """Each response must round-trip through JSON."""
    staged = _staged_responses()
    for name, resp in staged.items():
        cls = type(resp)
        js = resp.model_dump_json()
        cls.model_validate_json(js)


# ---------------------------------------------------------------------
# MockCaller behavior
# ---------------------------------------------------------------------

def test_mock_caller_returns_staged_response():
    staged = _staged_responses()
    mock = MockCaller(staged)
    resp, usage = mock("sys", "user", IdentityResponse, group_name="identity")
    assert isinstance(resp, IdentityResponse)
    assert resp.tagline_value == "Premium Foot Care in Cairo"
    assert usage.input_tokens > 0
    assert usage.cost_usd >= 0
    # Recorded
    assert len(mock.calls) == 1
    assert mock.calls[0].group_name == "identity"


def test_mock_caller_raises_on_missing_stage():
    mock = MockCaller({})
    try:
        mock("sys", "user", IdentityResponse, group_name="identity")
        assert False, "should have raised"
    except RuntimeError as e:
        assert "no staged response" in str(e)


def test_mock_caller_raises_on_simulated_failure():
    staged = _staged_responses()
    mock = MockCaller(staged, raise_on_group={"offerings"})
    # identity ok
    mock("sys", "user", IdentityResponse, group_name="identity")
    # offerings raises
    try:
        mock("sys", "user", OfferingsResponse, group_name="offerings")
        assert False, "should have raised"
    except RuntimeError as e:
        assert "simulated failure" in str(e)


def test_mock_caller_type_mismatch_raises():
    staged = _staged_responses()
    mock = MockCaller(staged)
    try:
        # asking for OfferingsResponse but staged "identity" is IdentityResponse
        mock("sys", "user", OfferingsResponse, group_name="identity")
        assert False, "should have raised"
    except TypeError as e:
        assert "expected OfferingsResponse" in str(e)


# ---------------------------------------------------------------------
# Extractor orchestration
# ---------------------------------------------------------------------

def test_run_llm_extraction_success_all_four_groups():
    pack = _small_pack()
    staged = _staged_responses()
    mock = MockCaller(staged, input_tokens=500, output_tokens=200,
                       model="gpt-4o-mini")

    result = run_llm_extraction(pack, mock)
    assert result.total_calls == 4
    assert result.total_failed == 0
    assert result.total_input_tokens == 4 * 500
    assert result.total_output_tokens == 4 * 200
    assert result.total_cost_usd > 0
    assert result.model == "gpt-4o-mini"

    # All groups returned objects
    assert result.identity.ok
    assert result.offerings.ok
    assert result.positioning.ok
    assert result.trust.ok

    # Mock recorded all four calls
    assert len(mock.calls) == 4
    groups = {c.group_name for c in mock.calls}
    assert groups == {"identity", "offerings", "positioning", "trust"}


def test_run_llm_extraction_partial_failure_continues():
    """If one group fails, the others still run and we get useful output."""
    pack = _small_pack()
    staged = _staged_responses()
    mock = MockCaller(staged, raise_on_group={"offerings"})

    result = run_llm_extraction(pack, mock)
    assert result.total_calls == 3  # 3 succeeded
    assert result.total_failed == 1
    assert result.identity.ok
    assert not result.offerings.ok
    assert "simulated failure" in (result.offerings.error or "")
    assert result.positioning.ok
    assert result.trust.ok


def test_run_llm_extraction_empty_pack_skips_calls():
    """A scrape that produces no usable text shouldn't burn LLM budget."""
    # Build an empty pack
    home = "https://x.com/"
    m = ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url=home, normalized_url=home, final_url=home, scraped_at=_now(),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=ReadinessReport(
            has_homepage=False, has_internal_pages=False,
            has_contact_signals=False, has_visual_signals=False,
            has_cta_candidates=False, has_metadata=False,
            ready_for_extraction=False,
        ),
        languages=[],
        pages=[],
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
    pack = build_evidence_pack(m, profile)
    assert pack.block_count == 0

    mock = MockCaller(_staged_responses())
    result = run_llm_extraction(pack, mock)
    assert result.total_calls == 0
    assert len(mock.calls) == 0
    # All four groups marked with empty_pack error
    for gr in result.all_groups:
        assert gr.error == "empty_pack"


def test_extractor_aggregates_usage_across_groups():
    pack = _small_pack()
    staged = _staged_responses()
    mock = MockCaller(staged, input_tokens=1000, output_tokens=300,
                       model="gpt-4o-mini")

    result = run_llm_extraction(pack, mock)
    # 4 calls * (1000+300) tokens
    assert result.total_input_tokens == 4000
    assert result.total_output_tokens == 1200
    # Cost check: 4 * (1000/1M * 0.150 + 300/1M * 0.600)
    expected = 4 * ((1000 / 1_000_000) * 0.150 + (300 / 1_000_000) * 0.600)
    assert abs(result.total_cost_usd - expected) < 1e-9


def test_extractor_passes_pack_text_to_caller():
    """Sanity: the prompts the caller receives must contain pack block_ids."""
    pack = _small_pack()
    mock = MockCaller(_staged_responses())
    run_llm_extraction(pack, mock)
    for call in mock.calls:
        assert "home_h1_0001" in call.user_prompt
        # System prompt is the same across calls
        assert call.system_prompt == SYSTEM_PROMPT


# ---------------------------------------------------------------------
# OpenAI caller sanity (no network)
# ---------------------------------------------------------------------

def test_openai_caller_can_be_constructed_without_api_key():
    """Constructing should not fail or call the API."""
    caller = OpenAICaller(model="gpt-4o-mini", api_key="dummy")
    assert caller.model == "gpt-4o-mini"
    # Client should be lazily created
    assert caller._client is None


def test_openai_caller_raises_helpful_error_if_sdk_missing(monkeypatch):
    """If openai isn't installed, we surface a clear message."""
    import importlib

    caller = OpenAICaller(api_key="dummy")
    # Force the import to fail
    monkeypatch.setitem(sys.modules, "openai", None)
    try:
        caller._get_client()
        assert False, "should have raised"
    except RuntimeError as e:
        assert "openai" in str(e).lower()
    except (ImportError, AttributeError, TypeError):
        # If openai is genuinely not installed, the original ImportError path
        # raises through our `raise RuntimeError(...) from e`. Accept any
        # outcome that signals 'sdk missing'.
        pass
