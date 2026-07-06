"""Opus creative director (reel.creative_director).

The Opus vision call needs a key + network; these tests cover the deterministic
parts: identity-block assembly, JSON parsing, and honest-degrade. The "designs a
real creative reel" behaviour is shown by the live elkbabgi run.
"""
from __future__ import annotations

from reel.creative_director import (
    _identity_block, _safe_json_object, _system_prompt, _vertical_mode, design_creative_reel,
)


def _profile():
    return {
        "name": {"value": "Qasr Elkbabgi"},
        "category": {"value": "restaurant"},
        "description": {"value": "An Egyptian grill."},
        "offerings": [{"name": "grilled dishes"}],
        "languages": ["ar", "en"],
    }


def test_identity_block_has_core_fields():
    b = _identity_block(_profile())
    assert "Qasr Elkbabgi" in b
    assert "grilled dishes" in b


def test_safe_json_object_strips_fences_and_handles_garbage():
    assert _safe_json_object('```json\n{"scenes":[]}\n```') == {"scenes": []}
    assert _safe_json_object("not json") is None


def test_no_key_degrades_to_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert design_creative_reel(_profile(), ["https://x.com/a.jpg"], api_key=None) is None


def test_no_photos_returns_none(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert design_creative_reel(_profile(), []) is None


# ---------------------------------------------------------------------
# Tone/vertical-aware direction (item 5: "show the jewelry WORN + elegance,
# tell the real story, minimal text"). The old prompt hard-coded FOOD dynamics
# into every reel.
# ---------------------------------------------------------------------

def test_vertical_mode_maps_brand_to_mode():
    assert _vertical_mode({"category": {"value": "restaurant"}}) == "food"
    assert _vertical_mode({"category": {"value": "jewelry"}}) == "elegant"
    assert _vertical_mode({"category": {"value": "fashion"}}) == "elegant"
    # a luxury TONE makes any vertical elegant (e.g. a jeweller tagged generic 'ecommerce')
    assert _vertical_mode({"category": {"value": "ecommerce"},
                           "tone_of_voice": {"value": "luxury"}}) == "elegant"
    assert _vertical_mode({"category": {"value": "clinic"}}) == "generic"


def test_elegant_prompt_is_worn_and_not_food():
    p = _system_prompt(5, "ar", "elegant")
    # elegance vocabulary: the product WORN, light on metal — NOT sizzling grills
    assert "WORN" in p and "elegant" in p.lower()
    assert "sizzling" not in p.lower() and "steam" not in p.lower()
    # minimal on-screen text is now a hard policy, not "a caption per scene"
    assert "TEXT-FREE" in p and "AT MOST" in p
    # a coherent STORY arc, heritage-aware, still fact-disciplined
    assert "STORY" in p and "never invent history" in p
    assert "invent NO facts" in p


def test_food_prompt_keeps_appetising_motion():
    p = _system_prompt(5, "en", "food")
    assert "steam" in p.lower() or "sizzling" in p.lower()
    assert "TEXT-FREE" in p                       # minimal-text policy is universal


def test_generic_prompt_has_no_food_or_worn_bias():
    p = _system_prompt(5, "en", "generic")
    assert "sizzling" not in p.lower()
    assert "cinematic MOTION" in p and "TEXT-FREE" in p
