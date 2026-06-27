"""Creative Concept layer + the Arabic LANGUAGE LOCK (build brief Steps B/C/D/E).

Hermetic: MockCaller only. No network.
"""
from __future__ import annotations

from poster.concept import (
    CreativeConcept, _ConceptResponse, brand_is_arabic, build_creative_concept, has_latin,
)
from business_profile.llm.caller import MockCaller

_AR = {
    "name": {"value": "WE"},
    "languages": ["en", "ar"],
    "description": {"value": "شركة المصرية للاتصالات تقدم خدمات الموبايل والإنترنت"},
    "offerings": [{"name": "مركز الاتصال المستضاف"}, {"name": "vehicle tracking"}],
}
_EN = {"name": {"value": "Acme"}, "languages": ["en"], "description": {"value": "A US shop"}}


def _resp(**kw) -> _ConceptResponse:
    base = dict(
        audience="عملاء", single_message="اتصال أقوى", core_benefit="سرعة",
        emotional_tone="ثقة", visual_idea="rim-lit subject under purple light beams",
        proof_points=["إنترنت أسرع", "تغطية أوسع"], headline="اتصالك أقوى",
        subheadline="جرّب الفرق", cta="اشترك الآن",
    )
    base.update(kw)
    return _ConceptResponse(**base)


def test_brand_is_arabic_detects_language_and_script():
    assert brand_is_arabic(_AR)
    assert not brand_is_arabic(_EN)


def test_has_latin():
    assert has_latin("Shop now")
    assert not has_latin("تسوق الآن")


def test_arabic_concept_passes_and_keeps_arabic_copy():
    c = build_creative_concept(_AR, caller=MockCaller({"poster_concept_brief": _resp()}))
    assert c.language == "ar"
    assert c.headline == "اتصالك أقوى" and not has_latin(c.headline)
    assert not has_latin(c.cta)
    assert c.proof_points == ["إنترنت أسرع", "تغطية أوسع"]


def test_latin_headline_regenerates_then_falls_back_no_latin():
    # The mock returns the SAME Latin headline every call -> retries exhausted -> grounded
    # Arabic fallback. The pipeline NEVER ships Latin on an Arabic brand.
    bad = _resp(headline="Faster connection", cta="Subscribe")
    c = build_creative_concept(_AR, caller=MockCaller({"poster_concept_brief": bad}), max_retries=1)
    assert not has_latin(c.headline)
    assert "fallback" in (c.note or "")


def test_arabic_brand_drops_latin_chips():
    c = build_creative_concept(
        _AR, caller=MockCaller({"poster_concept_brief": _resp(
            proof_points=["إنترنت أسرع", "vehicle tracking"])}))
    assert "إنترنت أسرع" in c.proof_points
    assert all(not has_latin(p) for p in c.proof_points)   # the Latin chip is dropped


def test_no_caller_grounded_fallback_is_arabic():
    c = build_creative_concept(_AR, caller=None)
    assert c.headline and not has_latin(c.headline) and c.language == "ar"


def test_english_brand_keeps_english():
    c = build_creative_concept(
        _EN, caller=MockCaller({"poster_concept_brief": _resp(
            headline="Built for builders", cta="Shop now", proof_points=["Fast", "Simple"])}))
    assert c.language == "en" and c.headline == "Built for builders"
