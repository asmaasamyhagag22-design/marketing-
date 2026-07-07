"""Domain-adaptive schema (business_profile.domain_schema).

The Gemini call needs creds + network; these tests cover the deterministic parts:
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


def test_no_caller_degrades_to_none(monkeypatch):
    # No Gemini caller available (bare env: no GOOGLE_CLOUD_PROJECT/GEMINI creds) -> honest None.
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert build_domain_profile(_profile()) is None


def test_injected_caller_is_grounded_and_none_when_nothing_survives(monkeypatch):
    # A fake caller lets us exercise the grounding filter hermetically (no network).
    from business_profile.domain_schema import _RawDomainField, _RawDomainResponse
    from business_profile.llm.caller import Usage

    prof = _profile()
    ev = _evidence_text(prof)

    def caller_grounded(system, user, response_model, group_name="", images=None):
        # one field whose quote is verbatim in the evidence -> kept
        quote = ev.split("\n")[0][:30]
        return (_RawDomainResponse(vertical="charcoal grill", rationale="why",
                                   fields=[_RawDomainField(key="cuisine", label="Cuisine",
                                                           value="grilled", evidence_quote=quote)]),
                Usage(model="gemini-2.5-pro"))
    dp = build_domain_profile(prof, caller=caller_grounded)
    assert dp is not None and dp.vertical == "charcoal grill" and dp.model == "gemini-2.5-pro"
    assert dp.fields and dp.fields[0].grounded

    def caller_invented(system, user, response_model, group_name="", images=None):
        return (_RawDomainResponse(vertical="x", fields=[_RawDomainField(
            key="fake", value="v", evidence_quote="THIS QUOTE IS NOT IN THE EVIDENCE AT ALL")]),
            Usage(model="gemini-2.5-pro"))
    assert build_domain_profile(prof, caller=caller_invented) is None   # ungrounded -> dropped -> None


def test_too_little_evidence_returns_none():
    # The <40-char evidence guard fires before any caller is consulted.
    assert build_domain_profile({"name": {"value": "Z"}}) is None
