# -*- coding: utf-8 -*-
"""U8b Discovery v2 slice — MarketDefinition query_seeds widen retrieval (hermetic).

The measured v1 gap: ONE offerings-built (usually English) query — Arabic-named local peers
never entered the candidate pool. Pins: bilingual seeds each hit Places, the union dedupes by
place_id, the v1 query stays FIRST, and an ungrounded definition degrades to exact v1."""
from __future__ import annotations

from competitor.discovery import discover_competitors
from competitor.market_definition import Geo, MarketDefinition
from competitor.models import Candidate


def _ef(value):
    return {"value": value, "evidence": [{"block_id": "b", "page_url": "https://x.example/",
                                          "quote": "q"}], "confidence": "high",
            "source_type": "inferred"}


# no address/coords -> the online-only path (no geocoding round-trips in the test)
_PROFILE = {"name": _ef("Qasr Elkbabgi"), "category": _ef("restaurant"),
            "physical_address": None,
            "offerings": [{"name": _ef("Grilled dishes")}], "languages": ["ar", "en"]}


class _FakeClient:
    """Records every text query; returns per-query candidates with one shared place_id."""

    def __init__(self, by_query):
        self.by_query = by_query
        self.queries: list[str] = []

    def search_text(self, q, **kw):
        self.queries.append(q)
        return self.by_query.get(q, [])

    def get_reviews(self, place_id):
        return []


def _cand(pid, name):
    return Candidate(place_id=pid, name=name, primary_type="restaurant",
                     rating=4.5, review_count=120, website=f"https://{pid}.example/")


def test_seeds_widen_the_pool_and_dedupe(monkeypatch):
    md = MarketDefinition(brand_ref="https://x.example/", category="restaurant",
                          geo=Geo(country="EG", city="Cairo"),
                          query_seeds=["مطعم مشويات القاهرة", "grill restaurant cairo"])
    monkeypatch.setattr("competitor.market_definition.build_market_definition",
                        lambda profile: md)
    v1_query = "grilled dishes restaurant"     # whatever v1 builds — captured below
    client = _FakeClient({})
    discover_competitors(_PROFILE, client, fetch_reviews=False)
    v1_query = client.queries[0]               # the actual v1 query, first by contract

    shared = _cand("p_shared", "El Dahan")     # returned by BOTH seeds -> must dedupe
    client = _FakeClient({
        v1_query: [_cand("p_en", "Grill House")],
        "مطعم مشويات القاهرة": [shared, _cand("p_ar", "مشويات أبو علي")],
        "grill restaurant cairo": [shared],
    })
    res = discover_competitors(_PROFILE, client, fetch_reviews=False)
    assert client.queries[0] == v1_query                      # v1 first, seeds after
    assert "مطعم مشويات القاهرة" in client.queries and "grill restaurant cairo" in client.queries
    assert any("v2 multi-seed retrieval: 3 queries -> 3 unique candidates" in n
               for n in res.notes)                            # 4 hits, 1 shared deduped


def test_ungrounded_definition_is_exact_v1(monkeypatch):
    monkeypatch.setattr("competitor.market_definition.build_market_definition",
                        lambda profile: MarketDefinition())   # not grounded
    client = _FakeClient({})
    res = discover_competitors(_PROFILE, client, fetch_reviews=False)
    assert len(client.queries) == 1                           # the single v1 query only
    assert not any("multi-seed" in n for n in res.notes)
