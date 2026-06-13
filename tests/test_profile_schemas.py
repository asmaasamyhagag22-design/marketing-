"""Tests for business_profile schemas.

Lock the contract before we build extractors. The state machine on
EvidencedField is the linchpin — if it breaks we get hallucinations
masquerading as facts.
"""
from datetime import datetime, timezone

import pytest

from business_profile.schemas import (
    BusinessCategory,
    BusinessProfile,
    Confidence,
    ContactChannels,
    EvidenceItem,
    EvidencedField,
    ExtractionMeta,
    LLMEvidenceRef,
    LLMStringField,
    Offering,
    ProfileQuality,
    SocialAccount,
    SourceType,
    ToneOfVoice,
    VisualIdentitySummary,
)


def _now():
    return datetime.now(timezone.utc)


def _minimal_meta() -> ExtractionMeta:
    return ExtractionMeta(
        manifest_path="scrapes/x/manifest.json",
        extracted_at=_now(),
    )


def _minimal_quality() -> ProfileQuality:
    return ProfileQuality(
        has_name=False, has_category=False, has_offerings=False,
        has_audience=False, has_value_propositions=False, has_tone=False,
        has_contact=False, has_visual=False,
        fields_extracted=0, fields_inferred=0, fields_missing=0,
        ready_for_strategy=False,
    )


def test_missing_field_defaults():
    f: EvidencedField[str] = EvidencedField.missing()
    assert f.value is None
    assert f.evidence == []
    assert f.confidence == Confidence.NONE
    assert f.source_type == SourceType.MISSING


def test_evidenced_field_with_evidence():
    f: EvidencedField[str] = EvidencedField(
        value="Cilantro",
        evidence=[EvidenceItem(
            block_id="home_h1_0001",
            page_url="https://x.com/",
            quote="Cilantro Cafe",
            extractor="rule:title",
        )],
        confidence=Confidence.HIGH,
        source_type=SourceType.EXTRACTED,
    )
    assert f.value == "Cilantro"
    assert len(f.evidence) == 1
    assert f.evidence[0].block_id == "home_h1_0001"


def test_enum_field():
    f: EvidencedField[BusinessCategory] = EvidencedField(
        value=BusinessCategory.RESTAURANT,
        evidence=[EvidenceItem(
            page_url="https://x.com/",
            extractor="schema_org:Restaurant",
        )],
        confidence=Confidence.HIGH,
        source_type=SourceType.EXTRACTED,
    )
    assert f.value == BusinessCategory.RESTAURANT


def test_profile_roundtrip_minimal():
    p = BusinessProfile(
        source_url="https://nti.sci.eg/",
        final_url="https://nti.sci.eg/",
        extraction_meta=_minimal_meta(),
        quality=_minimal_quality(),
    )
    js = p.model_dump_json()
    p2 = BusinessProfile.model_validate_json(js)
    assert p2.source_url == "https://nti.sci.eg/"
    # All fields default to missing
    assert p2.name.source_type == SourceType.MISSING
    assert p2.category.value is None


def test_profile_roundtrip_full():
    p = BusinessProfile(
        source_url="https://x.com/",
        name=EvidencedField(
            value="X Co",
            evidence=[EvidenceItem(
                block_id="home_h1_0001", page_url="https://x.com/",
                quote="X Co", extractor="rule:title",
            )],
            confidence=Confidence.HIGH,
            source_type=SourceType.EXTRACTED,
        ),
        category=EvidencedField(
            value=BusinessCategory.CLINIC,
            evidence=[EvidenceItem(
                page_url="https://x.com/", extractor="schema_org:MedicalClinic",
            )],
            confidence=Confidence.HIGH,
            source_type=SourceType.EXTRACTED,
        ),
        tone_of_voice=EvidencedField(
            value=ToneOfVoice.PROFESSIONAL,
            evidence=[EvidenceItem(
                block_id="home_p_0003", page_url="https://x.com/",
                quote="We deliver enterprise-grade...", extractor="llm",
            )],
            confidence=Confidence.MEDIUM,
            source_type=SourceType.INFERRED,
        ),
        offerings=[
            Offering(
                name="Premium consultation",
                short_description="One-hour expert review",
                price_text="from EGP 500",
                page_url="https://x.com/services",
                evidence=[EvidenceItem(
                    block_id="services_h3_0001", page_url="https://x.com/services",
                    quote="Premium consultation", extractor="llm",
                )],
            ),
        ],
        contact_channels=ContactChannels(
            phones_e164=["+201001234567"],
            emails=["info@x.com"],
            whatsapp_numbers=["+201001234567"],
            has_contact_form=True,
        ),
        social_presence=[
            SocialAccount(
                platform="instagram",
                url="https://instagram.com/xco",
                evidence=[EvidenceItem(
                    page_url="https://x.com/", extractor="rule:social_link",
                )],
            ),
        ],
        visual=VisualIdentitySummary(
            palette_hex=["#0a3d62", "#f5f5f5"],
            palette_dominance=[0.6, 0.4],
            primary_color="#0a3d62",
            logo_url="https://x.com/logo.svg",
        ),
        extraction_meta=_minimal_meta(),
        quality=_minimal_quality(),
    )
    js = p.model_dump_json(indent=2)
    p2 = BusinessProfile.model_validate_json(js)

    assert p2.name.value == "X Co"
    assert p2.name.source_type == SourceType.EXTRACTED
    assert p2.category.value == BusinessCategory.CLINIC
    assert p2.tone_of_voice.source_type == SourceType.INFERRED
    assert len(p2.offerings) == 1
    assert p2.offerings[0].price_text == "from EGP 500"
    assert p2.contact_channels.has_contact_form is True
    assert p2.social_presence[0].platform == "instagram"
    assert p2.visual.primary_color == "#0a3d62"


def test_llm_response_schema():
    """LLM-facing schemas are concrete (no generics) so they JSON-schema cleanly."""
    resp = LLMStringField(
        value="Premium coffee in Cairo",
        evidence=[LLMEvidenceRef(
            block_id="home_h1_0003",
            quote="Premium coffee in Cairo",
        )],
        confidence=Confidence.HIGH,
        reasoning="Direct match between H1 and a tagline-style phrase",
    )
    # Generate JSON schema — must succeed without errors for OpenAI structured outputs
    schema = LLMStringField.model_json_schema()
    assert "properties" in schema
    assert "value" in schema["properties"]
    assert "evidence" in schema["properties"]

    js = resp.model_dump_json()
    resp2 = LLMStringField.model_validate_json(js)
    assert resp2.evidence[0].block_id == "home_h1_0003"


def test_invariant_value_implies_evidence_or_missing():
    """A field with value!=None should have either evidence OR source_type=inferred.
    We don't enforce this in the model itself (Pydantic generics make it awkward),
    but the validator module will. Test that the state machine is at least
    representable cleanly."""
    # Missing state
    a: EvidencedField[str] = EvidencedField.missing()
    assert a.value is None and a.source_type == SourceType.MISSING

    # Extracted state (must have evidence)
    b: EvidencedField[str] = EvidencedField(
        value="X", evidence=[EvidenceItem(page_url="u", extractor="t")],
        confidence=Confidence.HIGH, source_type=SourceType.EXTRACTED,
    )
    assert b.value == "X" and len(b.evidence) >= 1

    # Inferred state (evidence is the basis, but not a direct quote of the value)
    c: EvidencedField[str] = EvidencedField(
        value="luxury",
        evidence=[EvidenceItem(page_url="u", extractor="llm",
                               quote="hand-crafted with imported materials")],
        confidence=Confidence.MEDIUM, source_type=SourceType.INFERRED,
    )
    assert c.source_type == SourceType.INFERRED
