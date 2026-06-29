"""Hermetic tests for the reel Motion/Music engine's PURE helpers (rhythm grid + xfade graph).
The ffmpeg render itself is verified live (out-of-CI)."""
from reel.motion import (
    _grid_durations, _xfade_offsets, _xfade_filtergraph, total_duration,
)


def test_grid_durations_hook_first_and_calmer_body():
    d = _grid_durations(4)
    assert len(d) == 4
    assert d[0] == 2.8                           # punchy HOOK first
    assert all(x >= 3.5 for x in d[1:])          # calmer ~4s body shots (no frantic <2s cuts)
    assert _grid_durations(0) == []


def test_grid_durations_a_3_shot_reel_is_no_longer_tiny():
    # the bug: 3 shots used to total ~4.5s. Now ~10s before the (smaller) xfade overlaps.
    d = _grid_durations(3)
    assert sum(d) >= 10.0


def test_grid_durations_snaps_to_beat_when_music_supplied():
    d = _grid_durations(3, bpm=120)              # beat = 0.5s
    assert all(abs(x / 0.5 - round(x / 0.5)) < 1e-6 for x in d)   # every cut on a beat


def test_xfade_offsets_accumulate_with_overlap():
    assert _xfade_offsets([1.0, 2.0, 2.0], 0.5) == [0.5, 2.0]   # d0-t, d0+d1-2t


def test_xfade_filtergraph_chains_and_labels():
    graph, label = _xfade_filtergraph(3, [1.0, 2.0, 2.0], 0.5)
    assert label == "[vout]"
    assert graph.count("xfade=") == 2                          # n-1 joins
    assert "[0:v][1:v]xfade" in graph and graph.endswith("[vout]")
    g1, l1 = _xfade_filtergraph(1, [1.0], 0.5)                 # single clip -> no xfade
    assert g1 == "" and l1 == "[0:v]"


def test_total_duration_subtracts_overlaps():
    assert total_duration([1.0, 2.0, 2.0], 0.5) == 4.0         # 5.0 - 2*0.5
    assert total_duration([], 0.5) == 0.0
