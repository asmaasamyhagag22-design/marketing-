"""Pre-render reel-plan evaluation (reel.plan_eval) — owner: 'evaluate the reel before it comes out'.

Deterministic gate that scores the PLAN (stranger test + caption craft) so a weak plan is caught and
regenerated before the expensive Veo render. Hermetic.
"""
from __future__ import annotations

from reel.creative_director import CreativeReel, CreativeScene
from reel.plan_eval import evaluate_reel_plan

_PROFILE = {
    "name": {"value": "ITI"}, "category": {"value": "education"},
    "offerings": [{"name": "Software Engineering Diploma"}, {"name": "Data Science Track"}],
}


def _scene(i, cap="", vo="", dur=3.0):
    return CreativeScene(image_index=i, veo_prompt=f"s{i}", on_screen_text=cap,
                         voiceover=vo, duration_s=dur)


def test_a_strong_plan_passes():
    reel = CreativeReel(cta="Apply now", scenes=[
        _scene(0, cap="ITI Diploma", vo="This is ITI, a tech-training institute."),
        _scene(1, cap="Job-ready fast", vo="Our Software Engineering diploma gets you hired."),
        _scene(2, cap="", vo="A Data Science track too."),
        _scene(3, cap="Apply now", vo="Apply to ITI today."),
    ])
    v = evaluate_reel_plan(reel, profile=_PROFILE)
    assert v.ok and v.score >= 80 and not v.issues


def test_a_vibe_plan_fails_the_stranger_test():
    # never names ITI or an offering, mostly text-free, all one photo -> a weak 'vibe' reel
    reel = CreativeReel(scenes=[
        _scene(0, cap="Your future", vo="Dream big."),
        _scene(0, cap="", vo="Anything is possible."),
        _scene(0, cap="", vo="Believe."),
    ])
    v = evaluate_reel_plan(reel, profile=_PROFILE)
    assert not v.ok
    joined = " ".join(v.issues).lower()
    assert "brand" in joined and "offering" in joined
    assert v.score < 60


def test_long_caption_and_empty_plan_are_flagged():
    long_cap = evaluate_reel_plan(CreativeReel(scenes=[
        _scene(0, cap="ITI Software Engineering diploma gets you hired in nine months", vo="ITI diploma"),
    ]), profile=_PROFILE)
    assert any("too long" in i for i in long_cap.issues)
    assert evaluate_reel_plan(CreativeReel(scenes=[]), profile=_PROFILE).ok is False
