"""Hermetic tests for the reel STORY CAPTIONS + VOICEOVER chain (the owner: "فين القصة؟" +
the TrendPulse insight "the reel should TALK"): schema -> build_brand_story returns aligned
captions/voiceovers -> the Ledger gate blanks an unsourced hard claim (drop-to-grounded) ->
pure caption-window math + the Veo voiceover clause. Live Imagen/Veo is out-of-CI."""
from __future__ import annotations

from reel.art_director import build_brand_story
from reel.generate import GeneratedReel, _caption_windows, _voiceover_clause
from reel.grounding import grounded_captions
from reel.motion import _acrossfade_filtergraph


class _Brief:
    business_name = "WE"
    category = "services_b2c"
    offerings = ["Fiber Internet", "eSIM"]
    tone = "premium"
    palette_hex = ["#512283"]
    headline = "Stay Close"
    subheadline = ""
    tagline = ""


class _Resp:
    character = "a young Egyptian engineer"
    scenes = ["Scene one.", "Scene two.", "Scene three."]
    captions = ["لحظة قرب", "شبكة بتقرّبنا"]      # shorter than scenes -> padded with ""
    voiceovers = ["كل مكالمة بتقرّبنا لبعض"]      # shorter than scenes -> padded with ""


def _caller(system, user, schema, group_name=""):
    assert "captions" in user                       # the prompt asks for the captions explicitly
    assert "voiceovers" in user                     # ... and the spoken lines
    return _Resp(), None


def test_build_brand_story_returns_aligned_captions_and_voiceovers():
    character, scenes, captions, voiceovers = build_brand_story(_Brief(), {}, _caller, n=3)
    assert character == "a young Egyptian engineer"
    assert len(scenes) == 3 and len(captions) == 3 and len(voiceovers) == 3  # aligned 1:1, padded
    assert captions == ["لحظة قرب", "شبكة بتقرّبنا", ""]
    assert voiceovers == ["كل مكالمة بتقرّبنا لبعض", "", ""]


def test_build_brand_story_no_caller_returns_empty_captions():
    assert build_brand_story(_Brief(), {}, None, n=3) == (None, [], [], [])


def test_voiceover_clause_dialect_is_universal_from_copy_and_cctld():
    eg = {"source_url": "https://te.eg/"}
    c = _voiceover_clause("كل مكالمة بتقرّبنا", eg)
    assert "Egyptian Arabic" in c and '"كل مكالمة بتقرّبنا"' in c    # .eg + Arabic copy -> Masri
    c2 = _voiceover_clause("أهلاً بكم", {"source_url": "https://brand.com/"})
    assert "Arabic" in c2 and "Egyptian" not in c2                   # Arabic elsewhere -> neutral
    c3 = _voiceover_clause("Stay close to what matters", eg)
    assert "English" in c3                                           # English copy -> English
    assert "no speech" in _voiceover_clause("", eg)                  # empty -> ambience only


def test_acrossfade_graph_mirrors_the_video_xfade_chain():
    graph, label = _acrossfade_filtergraph(3, 0.5)
    assert graph.count("acrossfade=d=0.5") == 2 and label == "[aout]"
    assert "[0:a][1:a]" in graph and "[2:a]" in graph                # chained in clip order
    assert _acrossfade_filtergraph(1, 0.5) == ("", "[0:a]")          # single clip: no chain


def test_grounded_captions_blanks_unsourced_hard_claim_keeps_paraphrase():
    profile = {"name": {"value": "WE"}}              # no evidence backs any hard claim
    caps = ["أكبر شبكة في مصر",                       # superlative/ranking, unsourced -> blanked
            "قرّبنا المسافات",                        # pure narrative paraphrase -> kept
            ""]                                       # empty stays empty (alignment preserved)
    assert grounded_captions(profile, caps) == ["", "قرّبنا المسافات", ""]


def test_caption_windows_sit_inside_each_clip_span():
    durs = [2.8, 4.4, 3.8]
    wins = _caption_windows(durs, 0.5)
    assert len(wins) == 3
    t = 0.5
    starts = [0.0, 2.8 - t, 2.8 + 4.4 - 2 * t]       # build_animated_reel's xfade math
    for (tin, tout), start, d in zip(wins, starts, durs):
        assert start <= tin < tout                    # opens after the incoming transition
        assert tout <= start + d - t + 0.01           # closes before the outgoing one
    assert _caption_windows([]) == []


def test_generated_reel_carries_caption_beats():
    r = GeneratedReel("x.mp4", [("لحظة قرب", 2.5, 5.9)])
    assert r.path == "x.mp4" and r.caption_beats[0][0] == "لحظة قرب"
