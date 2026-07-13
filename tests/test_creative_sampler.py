# -*- coding: utf-8 -*-
"""Creative-direction sampler — audience-filtered, reproducible, distinct-across-candidates.

Encodes the owner's principle: variety is a REQUIREMENT with its own mechanism, not chance —
so it must be deterministic under a seed, re-injectable, and audience-appropriate."""
from __future__ import annotations

from creative.sampler import (
    CreativeDirection, load_library, sample_direction, sample_distinct_directions,
)

_EDU = {"profile": {"category": {"value": "education"},
                    "audience_type": {"value": "students and career switchers"}}}
_FOOD = {"profile": {"category": {"value": "food"}, "audience_type": {"value": "diners"}}}


def _keys(kind):
    return {e["key"] for e in load_library(kind)}


def test_libraries_load_with_expected_entries():
    assert {"transformation", "day-in-the-life", "problem-agitate-solve", "before-after",
            "testimonial-style", "pov-challenge"} <= _keys("archetype")
    assert {"tool-of-trade", "journey-object", "sensory-food", "wearable",
            "workspace-object", "vehicle"} <= _keys("motif_domain")
    assert {"fresh-grad-f", "fresh-grad-m", "career-switcher", "small-business-owner",
            "parent", "student", "craftsman"} <= _keys("protagonist_slot")


def test_seed_is_reproducible():
    a = sample_direction(_EDU, seed=7)
    b = sample_direction(_EDU, seed=7)
    assert a == b and isinstance(a, CreativeDirection)
    assert a.archetype_desc and a.motif_domain_desc      # descriptions carried for the prompt


def test_forced_triple_reinjects_exactly():
    d = sample_direction(_EDU, forced={"archetype": "pov-challenge",
                                       "motif_domain": "journey-object",
                                       "protagonist_slot": "student"})
    assert d.triple == {"archetype": "pov-challenge", "motif_domain": "journey-object",
                        "protagonist_slot": "student"}


def test_audience_filter_excludes_ill_fitting_entries():
    # sensory-food should never be sampled for an EDUCATION brand (not in its audience_fit,
    # and not universal); over many seeds it must never appear.
    seen = {sample_direction(_EDU, seed=s).motif_domain for s in range(60)}
    assert "sensory-food" not in seen
    # ...but IS reachable for a food brand
    seen_food = {sample_direction(_FOOD, seed=s).motif_domain for s in range(60)}
    assert "sensory-food" in seen_food


def test_distinct_directions_have_distinct_archetypes():
    ds = sample_distinct_directions(_EDU, n=3, seed=1)
    assert len(ds) == 3
    assert len({d.archetype for d in ds}) == 3           # 3 different story shapes


def test_avoid_deprioritises_recent_keys():
    # avoiding an archetype key steers away from it when alternatives fit
    picks = {sample_direction(_EDU, seed=s, avoid=["transformation"]).archetype
             for s in range(40)}
    assert "transformation" not in picks
