# -*- coding: utf-8 -*-
"""Render #3 §1 variety mode — the 3-concept Director output + LOCALE parameterization.
Hermetic (fake caller returns a scripted DirectorOutput; no LLM)."""
from __future__ import annotations

import pytest

from creative.sampler import sample_direction
from reel.render3.director import (
    ConceptStub, DirectorOutput, concepts_distinct, direct_reel, direct_reel_concepts,
)
from tests.test_render3_director import _treatment

_PROFILE = {"profile": {"name": "NTI", "description": "telecom training institute",
                        "category": {"value": "education"},
                        "audience_type": {"value": "students"},
                        "value_propositions": ["hands-on labs"], "offerings": []}}


_STUBS = [
    ("a beam of light finally finds its way home", "a travelling beam of light",
     "a weary night-shift commuter"),
    ("an old locked door swings open for the bold", "an antique brass key",
     "a nervous fresh graduate"),
    ("the whole city map redraws itself around her ambition", "a folding paper map",
     "a proud small-shop owner"),
]


def _stub(i):
    big, motif, person = _STUBS[i]
    return ConceptStub(big_idea=big, logline=f"logline {i}", motif_object=motif,
                       protagonist_one_liner=person)


def _output():
    return DirectorOutput(concepts=[_stub(0), _stub(1), _stub(2)], picked_index=1,
                          treatment=_treatment(), direction_note="")


class _Caller:
    def __init__(self, out):
        self.out = out
        self.prompts = []

    def __call__(self, system, user, response_model, group_name="", images=None):
        assert group_name == "render3_director"
        self.prompts.append(user)
        return self.out, None


def test_concepts_call_returns_three_and_a_full_pick():
    direction = sample_direction(_PROFILE, seed=3)
    caller = _Caller(_output())
    out = direct_reel_concepts(_PROFILE, caller=caller, direction=direction)
    assert out is not None and len(out.concepts) == 3
    assert 0 <= out.picked_index < 3 and out.treatment.shots
    # the sampled direction + AVOID + R9 reached the prompt
    p = caller.prompts[0]
    assert direction.archetype in p and "R9 NOVELTY" in p and "AVOID" in p
    assert "first run" in p                               # empty avoid rendered honestly


def test_avoid_list_is_injected():
    caller = _Caller(_output())
    direct_reel_concepts(_PROFILE, caller=caller, direction=sample_direction(_PROFILE, seed=1),
                         avoid=["a reel about a tangled cable and a career-switcher"])
    assert "tangled cable" in caller.prompts[0]


def test_locale_defaults_to_egypt_but_is_overridable():
    caller = _Caller(_output())
    direct_reel_concepts(_PROFILE, caller=caller, direction=sample_direction(_PROFILE, seed=1))
    assert "LOCALE: Egypt" in caller.prompts[0]
    caller2 = _Caller(_output())
    direct_reel_concepts(_PROFILE, caller=caller2, direction=sample_direction(_PROFILE, seed=1),
                         locale="Morocco")
    # only the LOCALE line parameterizes; R8's "Egyptian Arabic" stays (R1-R8 unchanged)
    assert "LOCALE: Morocco" in caller2.prompts[0] and "LOCALE: Egypt" not in caller2.prompts[0]


def test_legacy_direct_reel_still_works_and_carries_locale():
    class _T:
        def __call__(self, system, user, response_model, group_name="", images=None):
            self.p = user
            return _treatment(), None
    c = _T()
    t = direct_reel(_PROFILE, caller=c)
    assert t is not None and "LOCALE: Egypt" in c.p and "R1 ONE PROTAGONIST" in c.p


def test_concepts_distinct_flags_near_duplicates():
    assert concepts_distinct(_output()) == []             # distinct motifs/ideas -> clean
    dup = DirectorOutput(
        concepts=[_stub(0), _stub(0), _stub(2)], picked_index=0,
        treatment=_treatment(), direction_note="")
    assert concepts_distinct(dup)                          # 0 and 1 identical -> flagged
