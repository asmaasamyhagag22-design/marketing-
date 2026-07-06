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
    # a luxury TONE makes a NON-beauty vertical elegant (e.g. a jeweller tagged generic 'ecommerce')
    assert _vertical_mode({"category": {"value": "ecommerce"},
                           "tone_of_voice": {"value": "luxury"}}) == "elegant"
    assert _vertical_mode({"category": {"value": "clinic"}}) == "generic"
    # a haircare/skincare brand (often just 'ecommerce') is detected as BEAUTY from its offerings
    assert _vertical_mode({"category": {"value": "ecommerce"},
                           "offerings": [{"name": "Hair Care"}, {"name": "Face Care"},
                                         {"name": "Lip Care"}]}) == "beauty"


def test_elegant_prompt_shows_the_piece_worn_alive_not_food():
    p = _system_prompt(5, "ar", "elegant")
    assert "WEARS" in p and ("ALIVE" in p or "alive" in p)     # worn + real movement, not a still
    assert "sizzling" not in p.lower() and "steam" not in p.lower()
    assert "TEXT-FREE" in p
    assert "AD SPINE" in p and "never invent history" in p and "invent NO facts" in p


def test_food_prompt_keeps_appetising_motion():
    p = _system_prompt(5, "en", "food")
    assert "steam" in p.lower() or "sizzling" in p.lower()
    assert "TEXT-FREE" in p


def test_every_mode_demands_people_action_and_is_grounded():
    # engineer/owner: the reel was a slow zoom on one still, no people. Every mode must now direct a
    # real PERSON using the product with energy, while the PRODUCT stays exactly as shown (grounded).
    for mode in ("beauty", "elegant", "food", "generic"):
        p = _system_prompt(5, "en", mode)
        assert "PERSON" in p                                   # a human in frame
        assert "NOT a slow zoom" in p                          # the exact defect, forbidden
        assert "stay exactly as shown" in p                    # product grounding preserved
    beauty = _system_prompt(5, "en", "beauty")
    assert "TikTok" in beauty and ("applies" in beauty or "sprays" in beauty)
    # the global directives: distinct photo per scene + a people self-check
    assert "DISTINCT photo" in beauty
    assert "PERSON using/reacting to the product" in beauty


def test_prompt_requires_an_ad_arc_so_the_reel_says_what_it_advertises():
    # Slice 3 (engineer: "I can't tell what it advertises"): the reel MUST name the brand + product
    # + benefit + CTA, be self-explanatory fast, and never drift into a store-kiosk montage.
    p = _system_prompt(5, "en", "generic")
    for beat in ("HOOK", "WHAT IT IS", "BENEFIT", "CTA"):
        assert beat in p, beat
    assert "by scene 2" in p                                  # self-explanatory in the first seconds
    assert "do NOT narrate store" in p and "kiosks" in p      # no vague brand/location montage
    assert "SELF-CHECK" in p and "NAMES the brand" in p       # closing verification
