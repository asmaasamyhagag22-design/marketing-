"""Domain-adaptive schema (business_profile.domain_schema).

The Claude call needs a key + network; these tests cover the deterministic parts:
evidence assembly, the code-enforced grounding check (so an invented attribute is
dropped), JSON parsing, and honest-degrade with no key. The "different verticals ->
different schemas" behaviour is shown by the live elkbabgi/digilians runs.
"""
from __future__ import annotations

from business_profile.domain_schema import (
    _PROMPT, _evidence_text, _is_grounded, _safe_json_object, build_domain_profile,
)


def test_prompt_requires_actionable_attributes():
    # The domain schema must yield attributes a marketer can ACT on (targeting/message/proof),
    # not trivia fields — so the generated schema feeds campaign decisions downstream.
    assert "a marketer could ACT on" in _PROMPT
    assert "targeting axis" in _PROMPT and "proof point" in _PROMPT


def _profile():
    return {
        "name": {"value": "Qasr Elkbabgi"},
        "category": {"value": "restaurant"},
        "description": {"value": "An Egyptian grill serving charcoal kebabs and molokhia."},
        "offerings": [{"name": "grilled dishes"}, {"name": "stuffed pigeon"}],
        "value_propositions": [{"value": "private farms under veterinary supervision"}],
        "languages": ["ar", "en"],
    }


def test_evidence_text_includes_real_fields():
    e = _evidence_text(_profile())
    assert "Qasr Elkbabgi" in e
    assert "grilled dishes" in e
    assert "veterinary supervision" in e


def test_grounding_accepts_verbatim_and_rejects_invented():
    evidence = _evidence_text(_profile())
    assert _is_grounded("charcoal kebabs and molokhia", evidence) is True
    assert _is_grounded("private farms under veterinary supervision", evidence) is True
    # An invented attribute with no support must fail the grounding gate.
    assert _is_grounded("Michelin three-star tasting menu with sommelier pairing", evidence) is False
    assert _is_grounded("", evidence) is False


def test_safe_json_object_strips_fences():
    assert _safe_json_object('```json\n{"vertical":"x","fields":[]}\n```') == {"vertical": "x", "fields": []}
    assert _safe_json_object("garbage") is None


def test_no_key_degrades_to_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert build_domain_profile(_profile(), api_key=None) is None


def test_too_little_evidence_returns_none(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert build_domain_profile({"name": {"value": "Z"}}) is None
