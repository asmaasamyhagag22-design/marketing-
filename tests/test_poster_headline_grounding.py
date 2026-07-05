"""H6 gate: an EXTERNAL poster headline (--headline, a content-calendar hook OR topic, or
a trend) must pass the SAME Evidence-Ledger grounding gate as the concept copy.

Regression origin (2026-07-05 audit): the poster used `headline_override or
concept.headline` — the override replaced the Ledger-gated concept headline WITHOUT being
gated itself. The strategy calendar's `topic` field is not gated, so a topic like "Egypt's
#1 pharmacy" reached the rendered poster verbatim, bypassing the moat.

Hermetic: the Evidence Ledger is built from a profile dict, no network / no LLM.
"""
from grounding import EvidenceLedger
from poster.pipeline import _verified_external_headline


def _ledger():
    profile = {
        "name": {"value": "Nahdi", "evidence": []},
        "description": {"value": "A pharmacy chain serving customers.", "evidence": []},
        "offerings": [{"name": "Medicines"}, {"name": "Personal care"}],
    }
    return EvidenceLedger.from_profile(profile)


def test_fabricated_override_falls_back_to_grounded_concept_headline():
    led = _ledger()
    # "#1" is an unsourced ranking/first claim -> must not render.
    hl, rem = _verified_external_headline("Egypt's #1 pharmacy", "Your trusted pharmacy", led)
    assert hl == "Your trusted pharmacy"
    assert rem is not None
    assert rem["action"] == "replaced_with_grounded_concept"
    assert "first" in rem["unsourced_claims"]


def test_unsourced_number_override_is_blocked():
    led = _ledger()
    hl, rem = _verified_external_headline("Save 70% today", "Your trusted pharmacy", led)
    assert hl == "Your trusted pharmacy"
    assert rem is not None and "number" in rem["unsourced_claims"]


def test_grounded_override_is_kept():
    led = _ledger()
    hl, rem = _verified_external_headline("Your trusted pharmacy", "Concept HL", led)
    assert hl == "Your trusted pharmacy"
    assert rem is None


def test_no_override_uses_concept_headline():
    led = _ledger()
    hl, rem = _verified_external_headline(None, "Concept HL", led)
    assert hl == "Concept HL" and rem is None


def test_ledger_unavailable_preserves_override_without_crashing():
    # Best-effort gate: if no ledger could be built, don't break rendering.
    hl, rem = _verified_external_headline("Egypt's #1 pharmacy", "Concept HL", None)
    assert hl == "Egypt's #1 pharmacy" and rem is None


def test_fabricated_override_drops_when_no_grounded_alternative():
    led = _ledger()
    hl, rem = _verified_external_headline("Egypt's #1 pharmacy", None, led)
    assert hl is None
    assert rem is not None and rem["action"] == "dropped"
