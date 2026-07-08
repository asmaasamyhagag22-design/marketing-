"""Batch 2 — the two shared poster prompt contracts and where they inject.

CRAFT_CONTRACT replaces the "senior / world-class / premium" priming that made every brand's
copy converge; VERBATIM_RENDER_CONTRACT is the frozen-strings rule shared by the one-shot
renderer and the OCR read-back reader. Hermetic (no network)."""
from __future__ import annotations

from poster.contracts import CRAFT_CONTRACT, VERBATIM_RENDER_CONTRACT
from poster.oneshot import build_oneshot_prompt


def test_craft_contract_sets_a_bar_and_bans_the_empty_primers():
    assert "CRAFT BAR" in CRAFT_CONTRACT
    for banned in ("premium", "world-class", "award-winning", "cutting-edge",
                   "unparalleled", "elevate", "unleash"):
        assert banned in CRAFT_CONTRACT                       # named as banned
    assert "Specificity replaces intensity" in CRAFT_CONTRACT
    assert "the FORM is yours" in CRAFT_CONTRACT              # facts gated, form free


def test_verbatim_render_contract_is_arabic_aware():
    assert "FROZEN strings" in VERBATIM_RENDER_CONTRACT
    assert "character-for-character" in VERBATIM_RENDER_CONTRACT
    assert "ة vs ه" in VERBATIM_RENDER_CONTRACT and "dot counts" in VERBATIM_RENDER_CONTRACT


def test_concept_system_uses_craft_contract_not_the_director_persona():
    import poster.concept as concept

    captured = {}
    class _Rec:
        def __call__(self, system, user, response_model, group_name="", images=None):
            captured["system"] = system
            captured["user"] = user
            # minimal valid concept
            return response_model(audience="a", single_message="m", core_benefit="b",
                                  emotional_tone="t", visual_idea="v", proof_points=[],
                                  headline="h", subheadline="s", cta="c"), None

    profile = {"name": {"value": "ITI"}, "languages": ["en"],
               "offerings": [{"name": "Software Engineering Diploma"}]}
    concept.build_creative_concept(profile, caller=_Rec(), arabic=False)
    s, u = captured["system"], captured["user"]
    assert "CRAFT BAR" in s                                   # the shared bar is injected
    assert "senior advertising CREATIVE DIRECTOR" not in s    # the priming persona is gone
    assert "STRANGER TEST" in s                               # the good part is kept
    assert "interchangeable concepts" in s                    # anti-convergence line
    # user prompt teaches jargon -> customer language without changing the facts
    assert "internal jargon" in u and "words a real customer would use" in u


def test_oneshot_prompt_injects_verbatim_contract_and_is_de_primed():
    p = build_oneshot_prompt({"headline": "H", "subheadline": "S", "cta": "C"},
                             brand_name="B", palette_names="brick red")
    assert VERBATIM_RENDER_CONTRACT in p                      # shared frozen-strings contract present
    assert "EXACTLY, character for character" in p            # the existing exact-render line stays
    assert "premium social-media advertising poster" not in p # de-primed opener
