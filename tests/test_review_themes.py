"""ReviewThemeExtractor — the review-theme extractor migrated from Anthropic to the shared
Gemini caller. Hermetic: an injected fake caller stands in for Gemini 2.5 Pro (no network).

The grounding is CODE-enforced (citations must resolve to real review IDs and clear the
support floor), so a fabricated citation is dropped regardless of what the model claims."""
from __future__ import annotations

from types import SimpleNamespace as NS

from business_profile.llm.caller import Usage
from competitor.themes import ReviewThemeExtractor, _ThemeItem, _ThemesResponse


def _comp(name, texts):
    return NS(candidate=NS(name=name), reviews=[NS(text=t, rating=5) for t in texts])


_COMPS = [
    _comp("Peer A", ["great coffee and fast service", "the coffee was great"]),
    _comp("Peer B", ["fast service, loved it", "coffee is great here too"]),
]


def _caller(themes):
    def call(system, user, response_model, group_name="", images=None):
        return _ThemesResponse(themes=themes), Usage(model="gemini-2.5-pro")
    return call


def test_grounded_theme_with_enough_citations_is_kept():
    caller = _caller([_ThemeItem(text="great coffee", polarity="praise",
                                 review_ids=["R1", "R2", "R4"])])
    ext = ReviewThemeExtractor(caller=caller, min_reviews_total=3,
                               min_support_reviews=2, min_support_peers=2)
    themes = ext(_COMPS)
    assert len(themes) == 1
    assert themes[0].polarity == "praise" and themes[0].text == "great coffee"
    assert ext.last_error is None


def test_fabricated_citation_is_dropped_by_code_grounding():
    # cites IDs that don't exist / don't clear the support floor -> dropped, even though the
    # model "returned" a theme. The moat is the code, not the model's word.
    caller = _caller([_ThemeItem(text="invented perk", polarity="praise", review_ids=["R99"])])
    ext = ReviewThemeExtractor(caller=caller, min_reviews_total=3,
                               min_support_reviews=2, min_support_peers=2)
    assert ext(_COMPS) == []


def test_no_caller_degrades_to_empty_with_reason(monkeypatch):
    for k in ("GOOGLE_CLOUD_PROJECT", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)         # no creds -> default_caller() is None
    ext = ReviewThemeExtractor(caller=None)
    assert ext(_COMPS) == []
    assert ext.last_error and "no Gemini caller" in ext.last_error


def test_too_few_reviews_skips_before_any_call():
    called = {"n": 0}
    def caller(*a, **k):
        called["n"] += 1
        return _ThemesResponse(), Usage(model="gemini-2.5-pro")
    ext = ReviewThemeExtractor(caller=caller, min_reviews_total=99)
    assert ext([_comp("Solo", ["only one review"])]) == []
    assert called["n"] == 0                          # never consulted the model
