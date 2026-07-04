"""Discovery adapter on a SERIALIZED (dict) profile — the web-API shape.

Regression for the measured root cause of the web app's always-standalone SWOT:
`build_match_criteria`'s `_get` did not unwrap a dict-shaped EvidencedField
({"value": ..., "evidence": [...]}), so the whole evidence dict leaked into the
Places text query as its repr — a garbage query -> 0 usable peers -> standalone
-> Threats/Opportunities permanently empty on the web path.

(The earlier fix recorded in CLAUDE.md covered the OBJECT path — str(enum) —
this covers the serialized-dict path the API actually sends.)
"""
from __future__ import annotations

from competitor.discovery import build_match_criteria


def _ef(value, quote="q", url="https://x.example/"):
    return {"value": value, "evidence": [{"block_id": "b", "page_url": url, "quote": quote}],
            "confidence": "high", "source_type": "inferred"}


_DICT_PROFILE = {
    "name": _ef("Qasr Elkbabgi"),
    "category": _ef("restaurant"),
    "physical_address": None,
    "offerings": [
        {"name": _ef("Grilled dishes"), "description": _ef("Eastern grills")},
    ],
    "languages": ["ar", "en"],
    "audience_type": _ef("mass market"),
}


def test_category_unwraps_clean_from_dict_evidenced_field():
    crit = build_match_criteria(_DICT_PROFILE)
    assert crit.category == "restaurant"
    # The Places type map resolves (it couldn't when category was the dict repr).
    assert crit.place_types, "restaurant must map to Places types"


def test_no_evidence_junk_leaks_into_the_query_keywords():
    crit = build_match_criteria(_DICT_PROFILE)
    joined = " ".join(crit.offering_keywords)
    for junk in ("value", "evidence", "block_id", "page_url", "confidence", "{", "'"):
        assert junk not in joined, f"evidence-dict junk {junk!r} leaked into the Places query"
    assert "grilled" in joined


def test_audience_tier_unwraps_from_dict():
    crit = build_match_criteria(_DICT_PROFILE)
    assert crit.audience_tier == "mid"   # "mass market" -> mid tier
