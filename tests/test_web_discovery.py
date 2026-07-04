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


# ---- identity-anchored query + relevance gate (the El Ezaby math-test bug) ----

_EZABY = {
    "name": {"value": "El Ezaby Pharmacy"},
    "source_url": "https://elezabypharmacy.com/",
    "category": {"value": "retail"},
    "description": {"value": "El Ezaby Pharmacy serves customers across Egypt"},
    "offerings": [
        {"name": {"value": "One Minute Clinic"}},
        {"name": {"value": "Basic Health Advice"}},
    ],
    "languages": ["en"],
}


def test_identity_terms_are_cross_field_corroborated():
    from competitor.web_discovery import _identity_terms
    terms = _identity_terms(_EZABY)
    # "pharmacy" is in the name + domain + description -> the identity.
    assert "pharmacy" in terms
    # Offering-only tokens (the garbage-query source) and pure brand words are OUT.
    for junk in ("one", "minute", "basic", "health", "ezaby"):
        assert junk not in terms


def test_query_is_anchored_on_identity_not_offering_soup():
    eng = SerpWebDiscoveryEngine(provider=None)
    queries, _hl = eng._queries(_EZABY)
    assert queries and queries[0].startswith("best ")
    assert "pharmacy" in queries[0]
    assert "minute" not in queries[0] and "basic" not in queries[0]


def test_relevance_gate_drops_unrelated_hits_keeps_real_peers():
    class MathTestProvider:
        name = "fake"
        def search(self, query, num=10, hl=None):
            return [
                SearchHit(title="One Minute Basic Number Facts Test",
                          link="https://mathtests.example/one-minute", snippet="math facts", rank=1),
                SearchHit(title="Westwood One Minute Basic Number Facts Test",
                          link="https://westwood.example/test", snippet="timed arithmetic", rank=2),
                SearchHit(title="Seif Pharmacy | Online Pharmacy in Egypt",
                          link="https://seif.example/", snippet="order medicine online", rank=3),
            ]
    eng = SerpWebDiscoveryEngine(MathTestProvider())
    peers = eng.discover(_EZABY)
    names = [p.candidate.name for p in peers]
    assert "Seif Pharmacy" in names            # the REAL peer survives
    assert not any("Number Facts" in n for n in names)   # the math tests are gone


def test_llm_judge_rejects_non_competitors_never_adds():
    class PoolProvider:
        name = "fake"
        def search(self, query, num=10, hl=None):
            return [
                SearchHit(title="Gardenia Pharmacies | pharmacy in Egypt",
                          link="https://gardeniapharmacies.example/", snippet="pharmacy branches", rank=1),
                SearchHit(title="Best Pharmacy Management Software",
                          link="https://medsoft.example/", snippet="pharmacy software listicle", rank=2),
                SearchHit(title="Best Universities in Pharmacy",
                          link="https://uniranks.example/", snippet="pharmacy programs", rank=3),
            ]

    class JudgeKeepsFirst:
        def __call__(self, system, user, response_model, group_name=""):
            return response_model(keep_indices=[0]), None

    eng = SerpWebDiscoveryEngine(PoolProvider(), judge_caller=JudgeKeepsFirst())
    peers = eng.discover(_EZABY)
    assert [p.candidate.name for p in peers] == ["Gardenia Pharmacies"]

    class JudgeBlowsUp:
        def __call__(self, *a, **k):
            raise RuntimeError("llm down")
    eng2 = SerpWebDiscoveryEngine(PoolProvider(), judge_caller=JudgeBlowsUp())
    peers2 = eng2.discover(_EZABY)
    assert len(peers2) == 3          # judge failure -> keep all (never breaks discovery)


def test_registrable_handles_multilabel_tlds():
    from competitor.web_discovery import _registrable
    # The naive last-two-labels guess collapsed every .com.eg host to "com.eg" —
    # deduping away real Egyptian peers and missing denylisted locale directories.
    assert _registrable("www.yellowpages.com.eg") == "yellowpages.com.eg"
    assert _registrable("gardeniapharmacies.com") == "gardeniapharmacies.com"
    assert _registrable("shop.example.co.uk") == "example.co.uk"


def test_llm_query_planner_leads_and_brand_leak_is_guarded():
    """The deterministic heuristic degraded to 'best nahdi' (a brand query -> only
    review sites -> 0 peers) on an Arabic-named brand whose identity words live in the
    description. The LLM planner writes the CUSTOMER's search (right language + market);
    a planned query that leaks the brand name is dropped; planner failure -> old path."""
    class _Provider:
        name = "fake"
        def __init__(self):
            self.queries = []
        def search(self, query, num=10, hl=None):
            self.queries.append(query)
            return []

    class _Planner:
        def __call__(self, system, user, response_model, group_name=""):
            assert "Homepage" in user            # the URL locale hint reaches the planner
            return response_model(
                queries=["أفضل صيدلية اون لاين السعودية",
                         "best El Ezaby deals"],   # brand leak -> must be dropped
                identity_terms=["صيدلية", "pharmacy"], market="Saudi Arabia"), None

    prov = _Provider()
    eng = SerpWebDiscoveryEngine(prov, judge_caller=_Planner())
    eng.discover(_EZABY)
    assert prov.queries[0] == "أفضل صيدلية اون لاين السعودية"   # planned query LEADS
    assert not any("ezaby deals" in q.lower() for q in prov.queries)  # leak dropped

    class _BoomPlanner:
        def __call__(self, *a, **k):
            raise RuntimeError("llm down")
    eng2 = SerpWebDiscoveryEngine(prov.__class__(), judge_caller=_BoomPlanner())
    eng2.discover(_EZABY)                          # planner failure -> never raises
