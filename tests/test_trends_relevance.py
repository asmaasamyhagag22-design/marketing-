# -*- coding: utf-8 -*-
"""Trend relevance + resilience (2026-07-05 audit).

The default sources (HN / Reddit / Dev.to) are TECH-skewed, so a plain word shared with a
tech headline is almost always a coincidence. The keyword matcher now drops bare
years/numbers and a broader set of generic + tech-ambiguous words, so a non-tech brand no
longer "matches" (and promotes) an irrelevant tech trend into its poster/strategy copy.
MEASURED: 24/45 corpus profiles false-matched a sample tech title before, 0/45 after.

`fetch_trends` also survives (and logs) a down / schema-drifted source instead of letting
one bad source break the aggregate.

Hermetic: mock sources / synthetic titles, no network.
"""
from trends.engine import keywords_from_profile, match_to_keywords, fetch_trends
from trends.sources import TrendItem


def _titles(*titles):
    return [TrendItem(source="hn", title=t, url="", score=5, created_ts=None) for t in titles]


def test_generic_and_numeric_keywords_are_dropped():
    prof = {"name": {"value": "X"},
            "tagline": {"value": "Free app since 2026 — world class data tools"},
            "offerings": [{"name": "coffee beans"}]}
    kws = keywords_from_profile(prof)
    for junk in ("free", "app", "2026", "world", "data", "tools"):
        assert junk not in kws
    assert "coffee" in kws and "beans" in kws


def test_non_tech_brand_does_not_match_a_generic_tech_title():
    items = _titles("New AI app released for developers in 2026",
                    "Show HN: a free tool for data pipelines")
    match_to_keywords(items, keywords_from_profile(
        {"name": {"value": "X"}, "tagline": {"value": "free app 2026 data"},
         "offerings": [{"name": "shoes"}]}))
    assert all(not it.matched_terms for it in items)     # no coincidental generic match


def test_real_keyword_still_matches():
    items = _titles("The best coffee roasters guide for 2026")
    match_to_keywords(items, ["coffee", "roast", "espresso"])
    assert items[0].matched_terms == ("coffee",)


def test_bare_numeric_keyword_never_matches():
    items = _titles("Top 10 releases of 2026")
    match_to_keywords(items, ["2026", "10"])
    assert not items[0].matched_terms


# --- fetch_trends resilience --------------------------------------------------------------
class _Src:
    def __init__(self, name, items=None, boom=False):
        self.name = name
        self._items = items or []
        self._boom = boom

    def fetch(self, limit):
        if self._boom:
            raise RuntimeError("source down / schema drift")
        return self._items


def test_fetch_trends_survives_a_failing_source():
    good = _Src("good", _titles("real trend"))
    bad = _Src("bad", boom=True)
    out = fetch_trends(sources=[bad, good, bad])
    assert len(out) == 1 and out[0].title == "real trend"   # good source still contributed


def test_fetch_trends_all_failing_returns_empty_not_crash():
    out = fetch_trends(sources=[_Src("a", boom=True), _Src("b", boom=True)])
    assert out == []
