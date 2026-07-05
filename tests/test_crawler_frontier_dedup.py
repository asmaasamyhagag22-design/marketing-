"""H3 gate: the crawl frontier collapses http/https and trailing-slash variants of the
same page onto ONE entry, so a budget-bound crawl doesn't spend two slots on it — while
still FETCHING a faithful URL (scheme unchanged; forcing https would break http-only sites).

Regression origin (measured 2026-07-05): orange.eg fetched both http+https and
trailing-slash variants of /contact-us and /services/... . `normalize_url` (the fetch
url) deliberately keeps the scheme distinct, so the dedup uses a separate scheme/slash-
insensitive `dedup_key`.

Hermetic: no network. Exercises `dedup_key` + `_select_subpages_to_fetch`.
"""
from scraper.crawler import _select_subpages_to_fetch
from scraper.url_utils import dedup_key, normalize_url
from scraper.schemas import LinkCategory


class _Link:
    def __init__(self, href, anchor="", category=LinkCategory.INTERNAL):
        self.href = href
        self.anchor_text = anchor
        self.category = category


def test_dedup_key_folds_scheme_and_slash_but_normalize_url_keeps_scheme():
    assert dedup_key("http://x.com/a") == dedup_key("https://x.com/a")
    assert dedup_key("https://x.com/a") == dedup_key("https://x.com/a/")
    # the FETCH url stays faithful to the original scheme
    assert normalize_url("http://x.com/a") == "http://x.com/a"
    # root is preserved, never stripped to empty
    assert dedup_key("https://x.com/") == "https://x.com/"


def test_frontier_collapses_variants_to_one_slot_each():
    site = "https://shop.example/"
    links = [
        _Link("http://shop.example/contact"),
        _Link("https://shop.example/contact"),    # scheme variant of the above
        _Link("https://shop.example/prices"),
        _Link("https://shop.example/prices/"),     # trailing-slash variant
    ]
    subs = _select_subpages_to_fetch(links, site, site, cap=30)
    urls = [s[0] for s in subs]
    keys = [dedup_key(u) for u in urls]
    assert len(keys) == len(set(keys)), f"duplicate frontier entries: {urls}"
    assert len(urls) == 2  # /contact and /prices, once each


def test_frontier_skips_homepage_variants():
    # A link that is just the homepage under a different scheme/slash is not a subpage.
    site = "https://shop.example/"
    links = [_Link("http://shop.example/"), _Link("https://shop.example")]
    subs = _select_subpages_to_fetch(links, site, site, cap=30)
    assert subs == []


def test_distinct_pages_still_selected():
    site = "https://shop.example/"
    links = [_Link("https://shop.example/a"), _Link("https://shop.example/b")]
    subs = _select_subpages_to_fetch(links, site, site, cap=30)
    assert len(subs) == 2
