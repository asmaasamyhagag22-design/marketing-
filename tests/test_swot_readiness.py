"""Readiness-gap Weaknesses (SWOT-quality Slice 4).

Brand-foundation Weaknesses from the grounded readiness audit — ONLY for a whitelisted signal that
is explicitly False (never inferred from a missing/irrelevant field). A well-scraped brand adds
none; a thin one surfaces real gaps. Crucially, `locations_with_geo`/`hours_known` being False for
an ONLINE brand is NOT a weakness (rule #4). Hermetic: no network/LLM.
"""
from __future__ import annotations

import dataclasses

from competitor.brand_signals import weaknesses_from_readiness
from competitor.matrix import build_matrix
from competitor.swot import synthesize_swot
from grounding import EvidenceLedger


def _thin_profile():
    return {
        "name": {"value": "Thin Co"},
        "readiness": {"swot_quality_signals": {
            "tagline": False,
            "value_propositions_3plus": False,
            "trust_signals_2plus": True,
            "multi_page_evidence": False,
            "pricing_posture_known": True,
            "offerings_3plus": True,
            "locations_with_geo": False,     # online brand -> NOT a weakness
            "hours_known": False,            # online brand -> NOT a weakness
        }},
    }


def test_thin_profile_surfaces_only_whitelisted_foundation_gaps():
    p = _thin_profile()
    weak = weaknesses_from_readiness(p, EvidenceLedger.from_profile(p))
    texts = [w.text for w in weak]
    assert any("tagline" in t.lower() for t in texts)
    assert any("value proposition" in t.lower() for t in texts)
    assert any("single page" in t.lower() for t in texts)
    # irrelevant-for-online False signals never become weaknesses
    assert not any("hour" in t.lower() or "location" in t.lower() or "geo" in t.lower() for t in texts)
    # provenance
    for w in weak:
        assert w.citation == ["your profile", "readiness audit"]
        assert w.claim_strength == "internally_supported"


def test_complete_profile_adds_no_readiness_weakness():
    ok = {"name": {"value": "Full Co"},
          "readiness": {"swot_quality_signals": {
              "tagline": True, "value_propositions_3plus": True, "trust_signals_2plus": True,
              "multi_page_evidence": True, "pricing_posture_known": True, "offerings_3plus": True}}}
    assert weaknesses_from_readiness(ok, EvidenceLedger.from_profile(ok)) == []
    # no readiness block at all -> also nothing (never invents)
    assert weaknesses_from_readiness({"name": {"value": "X"}}, EvidenceLedger.from_profile({})) == []


def test_synthesize_swot_appends_readiness_weaknesses_regression_safe():
    p = _thin_profile()
    m = build_matrix(p, [])
    after = synthesize_swot(m, profile=p)
    assert any("tagline" in w.text.lower() for w in after.weaknesses)   # supplementary gap present
    # regression: profile=None unchanged
    assert dataclasses.asdict(synthesize_swot(m, profile=None)) == dataclasses.asdict(synthesize_swot(m))
