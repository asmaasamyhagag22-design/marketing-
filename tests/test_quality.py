"""Tests for ProfileQuality computation."""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

# Stub playwright for local dev env
_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from business_profile.quality import compute_quality
from business_profile.schemas import (
    BusinessCategory,
    BusinessProfile,
    Confidence,
    ContactChannels,
    EvidenceItem,
    EvidencedField,
    ExtractionMeta,
    Offering,
    ProfileQuality,
    SocialAccount,
    SourceType,
    ToneOfVoice,
    VisualIdentitySummary,
)


def _now():
    return datetime.now(timezone.utc)


def _ev(extractor: str = "rule:test") -> EvidenceItem:
    return EvidenceItem(page_url="https://x.com/", extractor=extractor)


def _extracted_field(value, source_type=SourceType.EXTRACTED,
                     confidence=Confidence.HIGH) -> EvidencedField:
    return EvidencedField(
        value=value,
        evidence=[_ev()],
        confidence=confidence,
        source_type=source_type,
    )


def _empty_profile(**overrides) -> BusinessProfile:
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


# ---------------------------------------------------------------------
# Counts always sum to 20
# ---------------------------------------------------------------------

def test_empty_profile_all_missing():
    p = _empty_profile()
    q = p.quality
    assert q.fields_extracted == 0
    assert q.fields_inferred == 0
    assert q.fields_missing == 20
    assert q.ready_for_strategy is False
    # All has_* are false
    assert not any([q.has_name, q.has_category, q.has_offerings,
                    q.has_audience, q.has_value_propositions, q.has_tone,
                    q.has_contact, q.has_visual])


def test_counts_sum_to_20_with_partial_data():
    p = _empty_profile(
        name=_extracted_field("X Co"),
        contact_channels=ContactChannels(phones_e164=["+201001234567"]),
        visual=VisualIdentitySummary(palette_hex=["#0a3d62"]),
    )
    q = p.quality
    assert q.fields_extracted + q.fields_inferred + q.fields_missing == 20


# ---------------------------------------------------------------------
# has_name: STRICT — requires source_type=EXTRACTED
# ---------------------------------------------------------------------

def test_has_name_true_when_extracted():
    p = _empty_profile(name=_extracted_field("X Co"))
    assert p.quality.has_name is True


def test_has_name_false_when_inferred():
    """Names should never be inferred — has_name stays false."""
    p = _empty_profile(name=_extracted_field("X Co", SourceType.INFERRED))
    assert p.quality.has_name is False


def test_has_name_false_when_missing():
    p = _empty_profile()
    assert p.quality.has_name is False


# ---------------------------------------------------------------------
# has_category: allows extracted OR inferred
# ---------------------------------------------------------------------

def test_has_category_true_when_extracted():
    p = _empty_profile(category=_extracted_field(BusinessCategory.CLINIC))
    assert p.quality.has_category is True


def test_has_category_true_when_inferred_by_llm():
    p = _empty_profile(
        category=_extracted_field(BusinessCategory.RESTAURANT, SourceType.INFERRED)
    )
    assert p.quality.has_category is True


# ---------------------------------------------------------------------
# has_contact: any sub-field counts
# ---------------------------------------------------------------------

def test_has_contact_true_with_phone_only():
    p = _empty_profile(
        contact_channels=ContactChannels(phones_e164=["+201001234567"]),
    )
    assert p.quality.has_contact is True


def test_has_contact_true_with_form_only():
    p = _empty_profile(
        contact_channels=ContactChannels(has_contact_form=True),
    )
    assert p.quality.has_contact is True


def test_has_contact_true_with_map_only():
    p = _empty_profile(
        contact_channels=ContactChannels(map_embed_present=True),
    )
    assert p.quality.has_contact is True


def test_has_contact_false_when_all_empty():
    p = _empty_profile(contact_channels=ContactChannels())
    assert p.quality.has_contact is False


# ---------------------------------------------------------------------
# has_visual: logo OR palette
# ---------------------------------------------------------------------

def test_has_visual_true_with_logo_only():
    p = _empty_profile(
        visual=VisualIdentitySummary(logo_url="https://x.com/l.svg"),
    )
    assert p.quality.has_visual is True


def test_has_visual_true_with_palette_only():
    p = _empty_profile(
        visual=VisualIdentitySummary(palette_hex=["#0a3d62"]),
    )
    assert p.quality.has_visual is True


def test_has_visual_false_when_empty():
    p = _empty_profile(visual=VisualIdentitySummary())
    assert p.quality.has_visual is False


# ---------------------------------------------------------------------
# has_offerings / has_value_propositions: list non-empty
# ---------------------------------------------------------------------

def test_has_offerings_true_with_one_item():
    p = _empty_profile(
        offerings=[Offering(name="Consultation")],
    )
    assert p.quality.has_offerings is True


def test_has_value_propositions_true_when_list_non_empty():
    p = _empty_profile(
        value_propositions=[_extracted_field("Same-day appointments")],
    )
    assert p.quality.has_value_propositions is True


# ---------------------------------------------------------------------
# major_missing reports the right names
# ---------------------------------------------------------------------

def test_major_missing_lists_all_when_empty():
    p = _empty_profile()
    expected = {"category", "offerings", "audience_type",
                "value_propositions", "tone_of_voice"}
    assert set(p.quality.major_missing) == expected


def test_major_missing_drops_filled_fields():
    p = _empty_profile(
        category=_extracted_field(BusinessCategory.CLINIC),
        offerings=[Offering(name="Consultation")],
        tone_of_voice=_extracted_field(ToneOfVoice.PROFESSIONAL,
                                       SourceType.INFERRED),
    )
    expected = {"audience_type", "value_propositions"}
    assert set(p.quality.major_missing) == expected


# ---------------------------------------------------------------------
# ready_for_strategy gates correctly
# ---------------------------------------------------------------------

def test_ready_for_strategy_false_when_only_name():
    p = _empty_profile(name=_extracted_field("X Co"))
    assert p.quality.ready_for_strategy is False


def test_ready_for_strategy_false_when_missing_visual():
    p = _empty_profile(
        name=_extracted_field("X Co"),
        category=_extracted_field(BusinessCategory.CLINIC),
        offerings=[Offering(name="X")],
        contact_channels=ContactChannels(phones_e164=["+1"]),
        # No visual
    )
    assert p.quality.ready_for_strategy is False


def test_ready_for_strategy_true_when_all_five_present():
    p = _empty_profile(
        name=_extracted_field("X Co"),
        category=_extracted_field(BusinessCategory.CLINIC),
        offerings=[Offering(name="Consultation")],
        contact_channels=ContactChannels(emails=["x@x.com"]),
        visual=VisualIdentitySummary(logo_url="https://x.com/l.svg"),
    )
    assert p.quality.ready_for_strategy is True


# ---------------------------------------------------------------------
# Tally splits between extracted vs inferred
# ---------------------------------------------------------------------

def test_inferred_field_counts_under_inferred():
    p = _empty_profile(
        name=_extracted_field("X Co"),                              # extracted
        tone_of_voice=_extracted_field(ToneOfVoice.LUXURY,
                                       SourceType.INFERRED),         # inferred
    )
    q = p.quality
    assert q.fields_extracted >= 1
    assert q.fields_inferred >= 1


def test_field_with_value_but_no_source_type_treated_as_extracted():
    """Defensive: if an older file has value set with source_type=missing,
    we treat it as extracted (graceful migration)."""
    p = _empty_profile(
        name=EvidencedField(
            value="X Co", evidence=[_ev()],
            confidence=Confidence.HIGH,
            source_type=SourceType.MISSING,  # mismatched
        ),
    )
    # Graceful — but has_name remains False because we still require strict EXTRACTED
    # at the boolean level. The COUNT, however, treats it as extracted.
    q = p.quality
    assert q.fields_extracted >= 1
