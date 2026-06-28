"""Hermetic tests for the reel Motion/Music engine's PURE helpers (rhythm grid + xfade graph).
The ffmpeg render itself is verified live (out-of-CI)."""
from reel.motion import (
    _grid_durations, _xfade_offsets, _xfade_filtergraph, total_duration,
)


def test_grid_durations_hook_first_and_beat_aligned():
    d = _grid_durations(4, bpm=100, hook_beats=2, cycle_beats=(4, 3, 4))
    beat = 0.6                                   # 60/100
    assert len(d) == 4
    assert d[0] == round(2 * beat, 3)            # short HOOK first
    assert d[1] == round(4 * beat, 3) and d[2] == round(3 * beat, 3)   # varied cycle
    assert _grid_durations(0) == []


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
