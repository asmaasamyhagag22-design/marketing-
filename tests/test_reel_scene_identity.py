"""Universal identity-derived reel scene (reel/art_director) — hermetic, no LLM.

A brand whose category isn't a known template (telecom/fintech/logistics/...) must still get a
FIELD-RELEVANT deterministic scene from its scraped category + offerings (not a generic office),
with internal slug/segment labels (B2C / services_b2c) humanized out. Known verticals keep their
richer template (no regression).
"""
from __future__ import annotations

from poster.schemas import PosterBrief
from reel.art_director import _humanize, _identity_scene, build_scene_prompt


def _brief(category="", offerings=(), name="Brand"):
    return PosterBrief(business_name=name, headline=name, category=(category or None),
                       offerings=list(offerings))


def test_humanize_strips_slugs_and_segment_codes():
    assert _humanize("services_b2c") == "services"
    assert _humanize("Home-DSL") == "Home DSL"
    assert _humanize("B2B") == ""
    assert _humanize("logistics_b2b") == "logistics"


def test_identity_scene_is_field_relevant_no_jargon():
    b = _brief("services_b2c", ["Orange PREMIER", "GO packages"], name="Orange")
    s = _identity_scene(b, {"audience_type": {"value": "B2C"}})
    assert "real people" in s
    assert "Orange PREMIER" in s and "GO packages" in s
    assert "services_b2c" not in s and "b2c" not in s.lower()        # jargon humanized out
    assert "professional modern workplace" not in s                  # not the generic default


def test_unknown_category_uses_identity_not_generic_workplace():
    prompt = build_scene_prompt("intro", _brief("logistics_b2b", ["Same-day delivery"]), profile={})
    assert "Same-day delivery" in prompt
    assert "professional modern workplace" not in prompt
    assert "logistics_b2b" not in prompt


def test_known_vertical_keeps_its_template():
    prompt = build_scene_prompt("intro", _brief("education", ["Diploma"]), profile={})
    assert "learning space" in prompt   # the education template, not the identity fallback


# ---- marketing archetype -> reel scene composition (poster parity) ----

def test_build_scene_prompt_includes_archetype_cue():
    prompt = build_scene_prompt("intro", _brief("retail", ["Sneakers"]), profile={},
                                archetype="product_hero")
    assert "HERO" in prompt and "centered" in prompt          # product_hero composition cue
    assert "HERO" not in build_scene_prompt("intro", _brief("retail", ["Sneakers"]), profile={})


def test_reel_archetype_maps_category():
    from reel.storyboard import _reel_archetype
    assert _reel_archetype("ecommerce store") == "product_hero"
    assert _reel_archetype("telecom services") == "proof_and_trust"
    assert _reel_archetype("flash sale promo") == "typographic_anchor"
    assert _reel_archetype("restaurant") == "magazine_editorial"   # premium/lifestyle default
    assert _reel_archetype(None) == "magazine_editorial"


def test_build_storyboard_carries_archetype_into_scene_prompts():
    from reel.storyboard import build_storyboard
    b = _brief("ecommerce store", ["Sneakers"], name="Acme")
    # no real photos -> text-to-video scenes go through build_scene_prompt (get the archetype cue)
    sb = build_storyboard(b, profile={}, caller=None, selected_images=[])
    assert sb.marketing_archetype == "product_hero"
    assert any("HERO" in s.visual_prompt for s in sb.scenes)
    # a caller can OVERRIDE the derived archetype (e.g. to match the poster's chosen one)
    sb2 = build_storyboard(b, profile={}, caller=None, selected_images=[],
                           marketing_archetype="typographic_anchor")
    assert sb2.marketing_archetype == "typographic_anchor"
