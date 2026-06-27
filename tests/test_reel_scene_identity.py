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
