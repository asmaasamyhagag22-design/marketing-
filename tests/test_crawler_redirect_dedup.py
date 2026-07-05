"""H2 gate: the crawl frontier must not spend budget slots re-fetching a page it already
fetched under a different URL that redirects/normalizes to the same final page.

Regression origin (measured 2026-07-05): 9/110 corpus manifests carried duplicate pages
(22 wasted fetches). daturial.com fetched its homepage 5x (4 WordPress-internal URLs all
redirect to `/`, identical content_hash) — 4 of 11 subpage slots on a budget-bound crawl;
orange.eg fetched http+https and trailing-slash variants of the same page; mcdonalds.eg
fetched /Contact twice. The dedup is keyed on the normalized FINAL (post-redirect) url.

Hermetic: no network, no Playwright. Exercises the pure loop-guard `_register_fetched_or_skip`.
"""
from scraper.crawler import _register_fetched_or_skip


def _run(seed_final, subpage_finals):
    """Mirror the crawl loop: seed with the homepage final url, then feed each subpage's
    final url through the guard. Return the list of subpage final urls that were KEPT."""
    seen: set[str] = set()
    _register_fetched_or_skip(seed_final, seen)
    kept = []
    for fu in subpage_finals:
        if not _register_fetched_or_skip(fu, seen):
            kept.append(fu)
    return kept


def test_wordpress_internals_all_redirect_to_homepage_are_skipped():
    # daturial: 4 selected subpages all redirect to the homepage final url.
    kept = _run(
        "https://daturial.com/",
        ["https://daturial.com/", "https://daturial.com/",
         "https://daturial.com/", "https://daturial.com/about"],
    )
    assert kept == ["https://daturial.com/about"]  # only the genuinely distinct page kept


def test_two_requests_redirecting_to_same_final_collapse():
    # orange.eg / mcdonalds case: two different selected URLs that the SERVER resolves to
    # the same final page (the fetcher reports the same final_url) are deduped.
    kept = _run(
        "https://site.example/",
        ["https://www.mcdonalds.eg/Contact", "https://www.mcdonalds.eg/Contact"],
    )
    assert len(kept) == 1


def test_distinct_pages_are_all_kept():
    finals = ["https://site.example/a", "https://site.example/b", "https://site.example/c"]
    assert _run("https://site.example/", finals) == finals


def test_helper_records_and_reports_duplicate():
    seen: set[str] = set()
    assert _register_fetched_or_skip("https://x.example/p", seen) is False  # first: kept
    assert _register_fetched_or_skip("https://x.example/p", seen) is True   # repeat: skip
