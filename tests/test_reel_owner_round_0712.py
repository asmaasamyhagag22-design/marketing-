# -*- coding: utf-8 -*-
"""Owner round 2026-07-12 ('الريل البشع') — four measured root fixes, hermetic.

1. HITL SANCTITY: an EXECUTE-approved plan is FINAL — the pre-render eval may log, but a
   weak score must NEVER swap in a regenerated plan the user never saw.
2. LISTENABLE PACING: the VIDEO stretches to fit the words (~2.2 wps + a breath); the
   audio atempo squeeze is capped at 1.12x (1.35x was unintelligible).
3. EMOTIONAL ARC: every scene's voiceover_delivery reaches the narrator — the old code
   kept only the FIRST one, so a 'frustrated' hook directed the whole film.
4. FEATURED SEEDING: 'image_index ALWAYS 0' only when a real product photo anchors the
   pool; a photo-less offering (NTI course) draws on DIFFERENT real brand photos.
"""
from __future__ import annotations

from poster.schemas import PosterBrief
from reel.creative import build_creative_storyboard, render_creative_reel
from reel.creative_director import CreativeReel, CreativeScene, _system_prompt
from reel.plan_eval import ReelPlanVerdict
from reel.voiceover import _fit_filter, _instructions_for


def _plan(**kw) -> CreativeReel:
    base = dict(
        concept="c", hook="h", cta="قدم دلوقتي", language="ar",
        images=["https://x/0.jpg", "https://x/1.jpg"],
        scenes=[CreativeScene(image_index=0, veo_prompt="APPROVED SHOT ONE",
                              voiceover="بتجمع شهادات ومش لاقي فرصة؟",
                              voiceover_delivery="Relatable and slightly frustrated.",
                              on_screen_text="مش لاقي فرصة؟", duration_s=2.5),
                CreativeScene(image_index=1, veo_prompt="APPROVED SHOT TWO",
                              voiceover="في المعهد بنحول معرفتك لخبرة حقيقية مع أكاديمية المواهب المصرية",
                              voiceover_delivery="Confident and inviting.",
                              on_screen_text="خبرة حقيقية", duration_s=4.0)],
    )
    base.update(kw)
    return CreativeReel(**base)


def test_hitl_approved_plan_is_never_replaced_by_the_eval(monkeypatch, tmp_path):
    # The exact betrayal the owner caught: plan_eval scored her approved plan weak and the
    # renderer silently regenerated a different plan. Now: advisory log only.
    import reel.creative as rc
    import reel.plan_eval as pe

    monkeypatch.setattr(pe, "evaluate_reel_plan",
                        lambda *a, **k: ReelPlanVerdict(ok=False, score=0, issues=["weak"]))

    def _never(*a, **k):
        raise AssertionError("design_creative_reel must NOT run on an approved plan")
    monkeypatch.setattr(rc, "design_creative_reel", _never)

    captured: dict = {}

    def _fake_render(storyboard, **kw):
        captured["sb"] = storyboard
        return {"ok": True}
    monkeypatch.setattr(rc, "render_reel", _fake_render)

    plan = _plan()
    result, creative = render_creative_reel(
        {}, PosterBrief(business_name="NTI", headline="NTI"), [],
        provider=None, out_path=tmp_path / "r.mp4",
        plan_override=plan.model_dump(), with_voiceover=False)
    assert result == {"ok": True}
    # the APPROVED prompts render verbatim — nothing was swapped
    assert [s.visual_prompt for s in captured["sb"].scenes] == \
        ["APPROVED SHOT ONE", "APPROVED SHOT TWO"]
    assert creative.scenes[0].voiceover == "بتجمع شهادات ومش لاقي فرصة؟"


def test_narrated_scene_stretches_to_a_listenable_pace():
    # Her S2: 13 words squeezed into 4.0s (3.2 wps). The video must stretch to ~words/2.2.
    reel = _plan()
    sb = build_creative_storyboard(reel, PosterBrief(business_name="NTI", headline="NTI"))
    words = len(reel.scenes[1].voiceover.split())
    assert sb.scenes[1].duration_s >= round(0.3 + words / 2.2, 2)
    assert sb.scenes[1].duration_s <= 8.0


def test_audio_squeeze_capped_at_1_12x():
    # A read 33% too long must NOT be sped 1.33x (unintelligible) — 1.12x max.
    af = _fit_filter(raw_dur=25.0, total=19.0)
    assert "atempo=1.120" in af
    # a read that fits gets no speed-up at all
    assert "atempo" not in _fit_filter(raw_dur=10.0, total=19.0)


def test_full_emotional_arc_reaches_the_narrator():
    arc = ["Relatable and slightly frustrated", "Confident and inviting", "Proud and conclusive"]
    brief = _instructions_for(["س1", "س2", "س3"], arc, tone="")
    for d in arc:
        assert d in brief                       # EVERY direction, not just the first
    assert "ARC" in brief
    assert "never rush" in brief                # the anti-rush pace line, all moods
    # backward compat: a plain string still works
    assert "just this one" in _instructions_for(["x"], "just this one", tone="")


def test_featured_offering_without_photo_uses_varied_photos():
    anchored = _system_prompt(6, "ar", "generic", featured="X", product_photo_anchored=True)
    assert "ALWAYS 0" in anchored               # real product photo -> same-item shots
    unanchored = _system_prompt(6, "ar", "generic", featured="Fiber Course",
                                product_photo_anchored=False)
    assert "ALWAYS 0" not in unanchored         # photo-less course: never one photo x6
    assert "FEATURED OFFERING" in unanchored and "DIFFERENT" in unanchored
    # and the director now carries the hard pace budget
    assert "PACE BUDGET" in unanchored and "2 words per second" in unanchored
