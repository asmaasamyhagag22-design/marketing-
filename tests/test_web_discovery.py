"""SERP web-discovery engine: filtering, dedup, provenance, cap — no network."""
from __future__ import annotations

from competitor.search_providers import SearchHit
from competitor.web_discovery import SerpWebDiscoveryEngine


class FakeProvider:
    name = "fake"

    def __init__(self, hits_by_query=None, hits=None):
        self._by_query = hits_by_query or {}
        self._flat = hits or []
        self.calls = []

    def search(self, query, *, num=10, gl=None, hl=None):
        self.calls.append(query)
        if self._by_query:
            return self._by_query.get(query, [])
        return self._flat


def _profile(**over):
    p = {
        "name": {"value": "MyShop"},
        "category": {"value": "ecommerce"},
        "offerings": [{"name": "Running Shoes"}, {"name": "Sneakers"}],
        "languages": ["en"],
        "final_url": "https://www.myshop.com/",
    }
    p.update(over)
    return p


def test_returns_grounded_peers_with_provenance():
    hits = [
        SearchHit("Rival Runners | Best Shoes", "https://rivalrunners.com/", "", 1),
        SearchHit("SoleMates Store", "https://solemates.io/shop", "", 2),
    ]
    eng = SerpWebDiscoveryEngine(FakeProvider(hits=hits), max_peers=6)
    peers = eng.discover(_profile())

    assert len(peers) == 2
    assert peers[0].candidate.name == "Rival Runners"        # title cleaned at separator
    assert peers[0].candidate.website == "https://rivalrunners.com/"
    assert peers[0].has_scrapable_site is True
    assert peers[0].is_local is False
    assert "rank 1" in peers[0].selection.why_selected         # provenance: query + rank
    assert "query:" in peers[0].selection.why_selected


def test_filters_subject_social_and_aggregators():
    hits = [
        SearchHit("My Shop Official", "https://www.myshop.com/about", "", 1),  # subject -> drop
        SearchHit("Our Facebook", "https://facebook.com/something", "", 2),     # social -> drop
        SearchHit("On Amazon", "https://www.amazon.com/dp/x", "", 3),           # aggregator -> drop
        SearchHit("On Wikipedia", "https://en.wikipedia.org/wiki/Shoe", "", 4), # aggregator -> drop
        SearchHit("Real Rival", "https://realrival.com/", "", 5),               # keep
    ]
    eng = SerpWebDiscoveryEngine(FakeProvider(hits=hits))
    peers = eng.discover(_profile())

    domains = [p.candidate.website for p in peers]
    assert domains == ["https://realrival.com/"]


def test_dedups_by_registrable_domain_across_queries():
    by_q = {
        "MyShop competitors": [SearchHit("Rival", "https://rival.com/page-a", "", 1)],
        "MyShop alternatives": [SearchHit("Rival Again", "https://www.rival.com/page-b", "", 1)],
    }
    eng = SerpWebDiscoveryEngine(FakeProvider(hits_by_query=by_q))
    peers = eng.discover(_profile())
    assert len(peers) == 1                                    # same domain -> one peer


def test_respects_max_peers_cap():
    hits = [SearchHit(f"Rival {i}", f"https://rival{i}.com/", "", i) for i in range(1, 11)]
    eng = SerpWebDiscoveryEngine(FakeProvider(hits=hits), max_peers=3)
    peers = eng.discover(_profile())
    assert len(peers) == 3


def test_no_provider_returns_empty_never_raises():
    eng = SerpWebDiscoveryEngine(provider=None)
    assert eng.discover(_profile()) == []


def test_object_profile_is_supported():
    class EvField:
        def __init__(self, v): self.value = v

    class Prof:
        name = EvField("ObjShop")
        category = EvField("ecommerce")
        offerings = [{"name": "Widget"}]
        languages = ["en"]
        final_url = "https://objshop.com/"

    eng = SerpWebDiscoveryEngine(FakeProvider(hits=[SearchHit("Rival", "https://rival.com/", "", 1)]))
    peers = eng.discover(Prof())
    assert len(peers) == 1
    # subject correctly excluded even from an object profile
    eng2 = SerpWebDiscoveryEngine(FakeProvider(hits=[SearchHit("Self", "https://objshop.com/x", "", 1)]))
    assert eng2.discover(Prof()) == []
