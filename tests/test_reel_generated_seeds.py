# -*- coding: utf-8 -*-
"""FULLY-GENERATED reel scenes (owner creative ruling 2026-07-12) — hermetic.

Pins the REPURPOSING contract: real photos exit the DISPLAY path (generated seed is what
Veo animates) but expand as conditioning (REAL PLACE prompt block + attached photo) and as
the motion-QA judging reference (place_ref_url). Fail-closed: a seed that fails the gate
twice falls back to the REAL photo. Scope boundary: reels only — poster evidence surfaces
untouched (pinned by the poster suites)."""
from __future__ import annotations

from pathlib import Path

from poster.schemas import PosterBrief
from reel.creative import build_creative_storyboard
from reel.creative_director import CreativeReel, CreativeScene
from reel.seed_gen import build_seed_prompt, generate_scene_seeds


def _plan() -> CreativeReel:
    return CreativeReel(
        concept="c", hook="h", cta="قدم دلوقتي", language="ar",
        images=["https://x/real0.jpg", "https://x/real1.jpg"],
        scenes=[CreativeScene(image_index=0, veo_prompt="lab scene", voiceover="س",
                              duration_s=4.0),
                CreativeScene(image_index=1, veo_prompt="campus scene", voiceover="ص",
                              duration_s=4.0)])


def test_seed_prompt_carries_conditioning_and_bans():
    p = build_seed_prompt("a student coding in the lab", brand_name="NTI",
                          dna_lines="modern tech campus", locale_line="Set in Egypt.",
                          n_refs=1)
    assert "REAL PLACE" in p and "unmistakably lives THERE" in p
    assert "Do NOT paste" in p                       # fresh frame, not a photo copy
    assert "no text, letters, numbers, logos" in p   # the poster-grade no-text contract
    assert "Set in Egypt." in p and "modern tech campus" in p
    assert "9:16" in p and "a student coding in the lab" in p
    assert "REAL PLACE" not in build_seed_prompt("x", n_refs=0)   # honest without refs


def test_storyboard_maps_generated_seed_and_real_judging_ref():
    reel = _plan()
    brief = PosterBrief(business_name="NTI", headline="NTI")
    seeds = [("outputs/reels/_genseeds/seed_a.png", "https://x/real0.jpg"),
             (None, "https://x/real1.jpg")]          # scene 2: generation failed twice
    sb = build_creative_storyboard(reel, brief, seeds=seeds)
    s0, s1 = sb.scenes
    # scene 1: the GENERATED still is displayed; the REAL photo becomes the judge's reference
    assert s0.seed_image_url.endswith("seed_a.png")
    assert s0.place_ref_url == "https://x/real0.jpg"
    # scene 2 fail-closed: the REAL photo seeds (legacy), no self-judging reference
    assert s1.seed_image_url == "https://x/real1.jpg" and s1.place_ref_url is None
    # legacy mode (seeds=None) unchanged
    sb_old = build_creative_storyboard(reel, brief)
    assert sb_old.scenes[0].seed_image_url == "https://x/real0.jpg"
    assert sb_old.scenes[0].place_ref_url is None


def test_generate_scene_seeds_gate_retry_and_fallback(monkeypatch, tmp_path):
    import reel.seed_gen as sg

    calls = {"gen": 0, "prompts": []}

    def _fake_gen(prompt, out_path, **kw):
        calls["gen"] += 1
        calls["prompts"].append(prompt)
        Path(out_path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
        return Path(out_path)
    monkeypatch.setattr("poster.oneshot.generate_oneshot_poster", _fake_gen)
    monkeypatch.setattr(sg, "_ref_bytes", lambda url: (b"refbytes", "image/jpeg"))

    from reel.scene_qa import SeedVerdict
    verdicts = iter([SeedVerdict(overall_pass=True, checked=True),      # scene 1: pass
                     SeedVerdict(overall_pass=False, checked=True,      # scene 2: fail
                                 reason="warped"),
                     SeedVerdict(overall_pass=False, checked=True,      # scene 2 retry: fail
                                 reason="warped again")])
    monkeypatch.setattr("reel.scene_qa.check_seed_frame",
                        lambda p, caller=None, brand_hint="", log=None: next(verdicts))

    out = generate_scene_seeds(_plan(), ["https://x/real0.jpg", "https://x/real1.jpg"],
                               profile={"name": {"value": "NTI"}}, out_dir=tmp_path,
                               caller=object())
    assert len(out) == 2
    assert out[0][0] and out[0][1] == "https://x/real0.jpg"     # generated + judged vs real
    assert out[1][0] is None and out[1][1] == "https://x/real1.jpg"   # fail-closed fallback
    assert calls["gen"] == 3                                    # 1 + (1 retry) for scene 2
    assert "Natural anatomy" in calls["prompts"][-1]            # corrective retry suffix
