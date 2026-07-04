"""Explicit AR/EN output-language option for poster + reel (owner's choice) — hermetic.

Language is a DESIGN choice (two truth domains): the override steers the copy language;
the facts inside stay Ledger-gated regardless. "auto" preserves the old inference.
"""
from __future__ import annotations

from business_profile.llm.caller import MockCaller
from poster.concept import _ConceptResponse, brand_is_arabic, build_creative_concept
from reel.generate import _voiceover_clause


_AR_PROFILE = {
    "name": {"value": "قصر الكبابجي"},
    "languages": ["ar"],
    "tagline": {"value": "أشهى المشويات"},
    "offerings": [],
}

_EN_PROFILE = {
    "name": {"value": "Daturial"},
    "languages": ["en"],
    "tagline": {"value": "Autonomous AI Systems"},
    "offerings": [],
}


def test_concept_arabic_override_forces_language_lock_on_english_brand():
    # An ENGLISH brand + arabic=True: the fallback concept (no caller) must come out Arabic.
    c = build_creative_concept(_EN_PROFILE, caller=None, arabic=True)
    assert c.language == "ar"
    # And the reverse: an Arabic brand forced to English.
    c2 = build_creative_concept(_AR_PROFILE, caller=None, arabic=False)
    assert c2.language == "en"


def test_concept_auto_keeps_brand_inference():
    assert brand_is_arabic(_AR_PROFILE) is True
    c = build_creative_concept(_AR_PROFILE, caller=None)          # arabic=None -> inferred
    assert c.language == "ar"
    c2 = build_creative_concept(_EN_PROFILE, caller=None)
    assert c2.language == "en"


def test_concept_forced_arabic_rejects_latin_copy_from_llm():
    # The LLM returns ENGLISH copy while Arabic is FORCED -> the zero-Latin lock must
    # reject it and land on the Arabic fallback (never ships Latin).
    latin = _ConceptResponse(
        audience="aud", single_message="msg", core_benefit="ben", emotional_tone="warm",
        visual_idea="scene", proof_points=["Great grills"], headline="Best Grills",
        subheadline="Tasty food", cta="Order now")
    c = build_creative_concept(_AR_PROFILE, caller=MockCaller({"poster_concept_brief": latin}),
                               arabic=True, max_retries=0)
    assert c.language == "ar"
    assert not any(ch.isascii() and ch.isalpha() for ch in c.headline)


def test_voiceover_clause_language_override():
    # English text + forced Arabic -> Arabic dialect instruction (the owner's choice wins).
    ar = _voiceover_clause("A warm welcome", {"source_url": "https://x.eg/"}, language="ar")
    assert "Arabic" in ar
    # Arabic text + forced English -> English instruction.
    en = _voiceover_clause("أهلاً بيك", {"source_url": "https://x.eg/"}, language="en")
    assert "English" in en
    # auto keeps the old inference (Arabic text + .eg -> Masri).
    auto = _voiceover_clause("أهلاً بيك", {"source_url": "https://x.eg/"})
    assert "Masri" in auto or "Egyptian" in auto
    # Empty text stays ambience-only regardless.
    assert "no speech" in _voiceover_clause("", {}, language="ar")
