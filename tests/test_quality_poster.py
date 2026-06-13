"""Quality + merger regression tests for v0.2-b1.

Covers:
- compute_quality now produces ready_for_poster + poster_blockers
- Permissive offerings path: value props + audience can substitute
- Strict visual requirement: no palette and no logo → not poster-ready
- llm_silent_failure adds a blocker even when fields look OK
- Merger category fix: schema.org OTHER does NOT block better LLM category
- Merger preserves schema.org category when it's specific (non-OTHER)
- offerings_extraction_note propagation in merger
"""
from __future__ import annotations

import sys
import types
from copy import deepcopy
from datetime import datetime, timezone

# Stub playwright before importing scraper-dependent code
_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from business_profile.merger import merge_profile  # noqa: E402
from business_profile.quality import compute_quality  # noqa: E402
from business_profile.schemas import (  # noqa: E402
    AudienceType,
    BusinessCategory,
    BusinessProfile,
    Confidence,
    ContactChannels,
    EvidenceItem,
    EvidencedField,
    ExtractionMeta,
    Offering,
    ProfileQuality,
    SourceType,
    VisualIdentitySummary,
)


# ---------------------------------------------------------------------
# Helpers for building minimal valid BusinessProfile fixtures
# ---------------------------------------------------------------------

def _ev(extractor: str = "test", page_url: str = "https://x/", block_id: str = "b1") -> EvidenceItem:
    return EvidenceItem(
        block_id=block_id, page_url=page_url,
        quote="some text", extractor=extractor,
    )


def _field(value, source_type: SourceType = SourceType.EXTRACTED,
            confidence: Confidence = Confidence.HIGH,
            extractor: str = "test") -> EvidencedField:
    return EvidencedField(
        value=value,
        evidence=[_ev(extractor=extractor)] if value is not None else [],
        confidence=confidence if value is not None else Confidence.NONE,
        source_type=source_type if value is not None else SourceType.MISSING,
    )


def _make_profile(**overrides) -> BusinessProfile:
    """Build a BusinessProfile with sensible defaults; override per-test."""
    base = dict(
        schema_version="0.2.0",
        source_url="https://test.example/",
        name=_field("Test Business"),
        tagline=_field("Quality service", source_type=SourceType.INFERRED,
                       extractor="llm"),
        description=_field("A test business serving Cairo.",
                           source_type=SourceType.INFERRED, extractor="llm"),
        category=_field(BusinessCategory.SERVICES_B2C, extractor="schema_org"),
        offerings=[
            Offering(
                name="Service A", short_description="Test offering",
                price_text=None, page_url="https://test.example/",
                evidence=[_ev(extractor="llm")],
                confidence=Confidence.HIGH,
            ),
        ],
        pricing_visible=_field(False),
        pricing_posture=EvidencedField.missing(),
        audience_type=_field(AudienceType.B2C,
                              source_type=SourceType.INFERRED, extractor="llm"),
        audience_signals=[],
        value_propositions=[
            _field("Strong service", source_type=SourceType.INFERRED, extractor="llm"),
        ],
        tone_of_voice=EvidencedField.missing(),
        locations=[],
        service_areas=[],
        languages=["en"],
        hours=None,
        contact_channels=ContactChannels(
            phones_e164=["+201001234567"], emails=["info@test.example"],
            whatsapp_numbers=[], has_contact_form=False,
            physical_addresses=[], map_embed_present=False,
            evidence=[],
        ),
        existing_ctas=[],
        social_presence=[],
        trust_signals=[],
        visual=VisualIdentitySummary(
            palette_hex=["#0a3d62", "#ffffff"],
            palette_dominance=[0.5, 0.5],
            primary_color="#0a3d62",
            body_font="Inter", heading_font="Poppins",
            logo_url="https://test.example/logo.svg",
        ),
        extraction_meta=ExtractionMeta(
            manifest_path="m.json",
            manifest_hash=None,
            extracted_at=datetime.now(timezone.utc),
            duration_ms=0,
            rule_extractors_used=[],
            llm_calls=4,
            llm_tokens_input=400,
            llm_tokens_output=200,
            llm_model="gpt-4o-mini",
            llm_cost_usd=0.001,
            extractor_version="0.1.0",
        ),
        # quality is recomputed by the tests after construction
        quality=ProfileQuality(
            has_name=True, has_category=True, has_offerings=True,
            has_audience=True, has_value_propositions=True, has_tone=False,
            has_contact=True, has_visual=True,
            fields_extracted=10, fields_inferred=5, fields_missing=5,
            major_missing=[], ready_for_strategy=True,
        ),
        offerings_extraction_note=None,
        llm_silent_failure=False,
        final_url=None,
    )
    base.update(overrides)
    return BusinessProfile(**base)


# ---------------------------------------------------------------------
# ready_for_poster — happy path
# ---------------------------------------------------------------------

def test_ready_for_poster_passes_for_well_formed_profile():
    """All gates satisfied → ready_for_poster=True, no blockers."""
    p = _make_profile()
    p.quality = compute_quality(p)
    assert p.quality.ready_for_poster is True
    assert p.quality.poster_blockers == []


def test_ready_for_poster_falls_back_to_value_props_when_offerings_empty():
    """No offerings, but value_props + audience present → poster-ready."""
    p = _make_profile(offerings=[])
    p.quality = compute_quality(p)
    assert p.quality.has_offerings is False
    # value_propositions + audience_type present in the fixture
    assert p.quality.ready_for_poster is True
    assert "no_offer_or_strong_positioning" not in p.quality.poster_blockers


# ---------------------------------------------------------------------
# ready_for_poster — blocker enumeration
# ---------------------------------------------------------------------

def test_ready_for_poster_fails_when_no_visual_signals():
    """No palette, no logo → not poster-ready, regardless of other fields."""
    p = _make_profile(visual=VisualIdentitySummary(
        palette_hex=[], palette_dominance=[], primary_color=None,
        body_font=None, heading_font=None, logo_url=None,
    ))
    p.quality = compute_quality(p)
    assert p.quality.ready_for_poster is False
    assert "no_visual_signals" in p.quality.poster_blockers


def test_ready_for_poster_fails_with_no_offerings_and_no_value_props():
    p = _make_profile(offerings=[], value_propositions=[])
    p.quality = compute_quality(p)
    assert p.quality.ready_for_poster is False
    assert "no_offer_or_strong_positioning" in p.quality.poster_blockers


def test_ready_for_poster_fails_with_no_brand_statement():
    """No description, no value_props, no tagline → no_brand_statement blocker."""
    p = _make_profile(
        description=EvidencedField.missing(),
        tagline=EvidencedField.missing(),
        value_propositions=[],
    )
    p.quality = compute_quality(p)
    assert "no_brand_statement" in p.quality.poster_blockers


def test_ready_for_poster_blocked_by_llm_silent_failure_even_with_fields():
    """When the LLM silently failed, poster gen must be blocked even
    if individual fields look populated (they may be stale or wrong)."""
    p = _make_profile(llm_silent_failure=True)
    p.quality = compute_quality(p)
    assert p.quality.ready_for_poster is False
    assert "llm_silent_failure" in p.quality.poster_blockers


def test_pricing_not_required_for_poster_gate():
    """Pricing missing must NOT block poster generation (per b1 spec)."""
    p = _make_profile(
        pricing_visible=EvidencedField.missing(),
        pricing_posture=EvidencedField.missing(),
    )
    p.quality = compute_quality(p)
    assert p.quality.ready_for_poster is True


# ---------------------------------------------------------------------
# Merger category fix: schema.org OTHER must not block LLM
# ---------------------------------------------------------------------

def _make_minimal_rules_profile(category_field: EvidencedField) -> BusinessProfile:
    """A bare-bones rules-only profile for testing _merge_category."""
    return _make_profile(category=category_field, offerings=[])


def test_merger_schema_org_other_yields_to_llm_category():
    """The b1 bug fix: when rules category is schema.org -> OTHER,
    the LLM-inferred restaurant/education/etc. must win."""
    from business_profile.llm.validator import ValidatedScalarField
    rules_p = _make_minimal_rules_profile(_field(
        BusinessCategory.OTHER, extractor="schema_org",
    ))
    # Build a minimal ValidatedPayload with an LLM-inferred category.
    from business_profile.llm.validator import (
        ValidatedIdentity, ValidatedPayload, ValidationDiagnostics,
    )
    llm_category = ValidatedScalarField(
        value=BusinessCategory.RESTAURANT,
        evidence=[_ev(extractor="llm")],
        confidence=Confidence.HIGH, inferred=True,
    )
    identity = ValidatedIdentity(
        tagline=ValidatedScalarField(value=None, evidence=[],
                                       confidence=Confidence.NONE, inferred=False),
        description=ValidatedScalarField(value=None, evidence=[],
                                           confidence=Confidence.NONE, inferred=False),
        category=llm_category,
    )
    payload = ValidatedPayload(
        identity=identity, offerings=None, positioning=None, trust=None,
        diagnostics=ValidationDiagnostics(),
    )
    merged = merge_profile(rules_p, payload, llm_result=None, expected_llm=False)
    assert merged.category.value == BusinessCategory.RESTAURANT


def test_merger_schema_org_specific_category_wins_over_llm():
    """Inverse: when schema.org gives a specific category (CLINIC),
    LLM should NOT override it."""
    from business_profile.llm.validator import (
        ValidatedIdentity, ValidatedPayload, ValidatedScalarField,
        ValidationDiagnostics,
    )
    rules_p = _make_minimal_rules_profile(_field(
        BusinessCategory.CLINIC, extractor="schema_org",
    ))
    # LLM tries to say it's a restaurant — wrong, ignore.
    llm_category = ValidatedScalarField(
        value=BusinessCategory.RESTAURANT,
        evidence=[_ev(extractor="llm")],
        confidence=Confidence.LOW, inferred=True,
    )
    identity = ValidatedIdentity(
        tagline=ValidatedScalarField(value=None, evidence=[],
                                       confidence=Confidence.NONE, inferred=False),
        description=ValidatedScalarField(value=None, evidence=[],
                                           confidence=Confidence.NONE, inferred=False),
        category=llm_category,
    )
    payload = ValidatedPayload(
        identity=identity, offerings=None, positioning=None, trust=None,
        diagnostics=ValidationDiagnostics(),
    )
    merged = merge_profile(rules_p, payload, llm_result=None, expected_llm=False)
    # schema.org CLINIC wins
    assert merged.category.value == BusinessCategory.CLINIC


def test_merger_no_schema_org_lets_llm_set_category():
    """When rules have no category at all, LLM-inferred wins."""
    from business_profile.llm.validator import (
        ValidatedIdentity, ValidatedPayload, ValidatedScalarField,
        ValidationDiagnostics,
    )
    rules_p = _make_minimal_rules_profile(EvidencedField.missing())
    llm_category = ValidatedScalarField(
        value=BusinessCategory.EDUCATION,
        evidence=[_ev(extractor="llm")],
        confidence=Confidence.HIGH, inferred=True,
    )
    identity = ValidatedIdentity(
        tagline=ValidatedScalarField(value=None, evidence=[],
                                       confidence=Confidence.NONE, inferred=False),
        description=ValidatedScalarField(value=None, evidence=[],
                                           confidence=Confidence.NONE, inferred=False),
        category=llm_category,
    )
    payload = ValidatedPayload(
        identity=identity, offerings=None, positioning=None, trust=None,
        diagnostics=ValidationDiagnostics(),
    )
    merged = merge_profile(rules_p, payload, llm_result=None, expected_llm=False)
    assert merged.category.value == BusinessCategory.EDUCATION


# ---------------------------------------------------------------------
# Merger offerings_extraction_note propagation
# ---------------------------------------------------------------------

def test_merger_clears_offerings_note_when_offerings_populated():
    """A previously-empty offerings note must be cleared when offerings exist."""
    from business_profile.llm.extractor import LLMExtractionResult, GroupResult
    from business_profile.llm.validator import (
        ValidatedOfferings, ValidatedOffering, ValidatedPayload,
        ValidatedScalarField, ValidationDiagnostics,
    )
    rules_p = _make_profile(
        offerings=[],
        offerings_extraction_note="llm_skipped",  # stale
    )
    # LLM returns one valid offering
    offerings = ValidatedOfferings(
        offerings=[ValidatedOffering(
            name="New offering", short_description=None, price_text=None,
            evidence=[_ev(extractor="llm")],
            confidence=Confidence.HIGH,
        )],
        pricing_posture=ValidatedScalarField(
            value=None, evidence=[], confidence=Confidence.NONE,
            inferred=False,
        ),
    )
    payload = ValidatedPayload(
        identity=None, offerings=offerings,
        positioning=None, trust=None,
        diagnostics=ValidationDiagnostics(),
    )
    llm_result = LLMExtractionResult(
        identity=GroupResult(group="identity", error="x"),
        offerings=GroupResult(group="offerings", error=None),
        positioning=GroupResult(group="positioning", error="x"),
        trust=GroupResult(group="trust", error="x"),
        total_calls=1, total_failed=3,
        model="gpt-4o-mini",
    )
    merged = merge_profile(rules_p, payload, llm_result, expected_llm=True)
    assert len(merged.offerings) == 1
    # Note cleared
    assert merged.offerings_extraction_note is None
