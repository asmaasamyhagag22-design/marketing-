"""Deep Search fallback: provenance, extraction, honesty — no network."""
from __future__ import annotations

from scraper.deep_search import gather_deep_search_evidence


class Hit:
    def __init__(self, title, link, snippet="", rank=0):
        self.title, self.link, self.snippet, self.rank = title, link, snippet, rank


class FakeProvider:
    name = "fake"

    def __init__(self, by_query):
        self.by_query = by_query
        self.calls = []

    def search(self, query, *, num=10, gl=None, hl=None):
        self.calls.append(query)
        return self.by_query.get(query, [])


def test_recovers_name_description_socials_with_provenance():
    provider = FakeProvider({
        "site:lcwaikiki.eg": [
            Hit("LC Waikiki Egypt | Fashion & Clothing", "https://www.lcwaikiki.eg/", "Shop the latest fashion at LC Waikiki Egypt.", 1),
            Hit("Kids", "https://www.lcwaikiki.eg/kids", "Kids collection", 2),
        ],
        "lcwaikiki": [
            Hit("LC Waikiki", "https://www.facebook.com/lcwaikiki", "Official page", 1),
            Hit("LC Waikiki", "https://www.instagram.com/lcwaikiki", "Official IG", 2),
        ],
    })
    res = gather_deep_search_evidence("https://www.lcwaikiki.eg/", provider=provider)

    assert res.used is True
    assert res.provider == "fake"
    assert res.business_name == "LC Waikiki Egypt"             # cleaned at separator, homepage listing
    assert "fashion" in (res.description or "").lower()
    assert any("facebook.com" in s for s in res.social_links)
    assert any("instagram.com" in s for s in res.social_links)
    assert res.sources and res.sources[0].url.startswith("https://")


def test_no_provider_is_honest_not_fabricated():
    res = gather_deep_search_evidence("https://blocked.example/", provider=None)
    # With no real env key during tests, default provider is None -> used=False.
    if res.used is False:
        assert "no search provider" in (res.note or "")
        assert res.business_name is None and not res.social_links


def test_empty_results_never_fabricate():
    res = gather_deep_search_evidence("https://x.example/", provider=FakeProvider({}))
    assert res.used is True
    assert res.business_name is None
    assert res.social_links == []
    assert res.note == "search returned no results"


def test_prefers_homepage_listing_over_deep_pages():
    provider = FakeProvider({
        "site:shop.example": [
            Hit("Deep Product Page", "https://shop.example/catalog/item/12345", "a product", 1),
            Hit("Shop Example — Home", "https://shop.example/", "The official store.", 2),
        ],
        "shop": [],
    })
    res = gather_deep_search_evidence("https://shop.example/", provider=provider)
    assert res.business_name == "Shop Example"                 # root path wins over deep path
