"""H1 gate: the adaptive e-commerce budget must not hinge on a single homepage snapshot.

Regression origin (measured 2026-07-05): the store signal was computed ONCE from the
homepage's rendered links. A JS store can under-render that snapshot nondeterministically
— nahdionline.com, same morning, same dead sitemap, produced a homepage with 2 product
links on one run (stayed at 12-page/150s budget -> 6 pages) and 164 on another (30-page/
330s -> 24 pages): 4x coverage variance on identical input, silently. The fix re-evaluates
the signal over ACCUMULATED links inside the crawl loop and upgrades the budget once the
product-URL density crosses the threshold.

Offline-validated on real data: nahdi's failing 6-page manifest carried 15 product URLs
across the pages it DID fetch (homepage-only = 2) — enough to flip mid-crawl.

Hermetic: no network. Exercises the real `_looks_like_ecommerce` the loop calls, mirroring
the loop's re-evaluate-and-upgrade logic.
"""
from scraper.crawler import _looks_like_ecommerce
from scraper.config import (
    MAX_INTERNAL_PAGES,
    ECOMMERCE_MAX_INTERNAL_PAGES,
    TOTAL_BUDGET_SECONDS,
    ECOMMERCE_BUDGET_SECONDS,
    ECOMMERCE_PRODUCT_URL_MIN,
)


class _Link:
    def __init__(self, href):
        self.href = href


def test_homepage_snapshot_under_renders_but_accumulated_links_flip_the_signal():
    # The nahdi failing-run shape: homepage exposes only a couple of product links.
    home = [
        _Link("https://shop.example/products/a"),
        _Link("https://shop.example/products/b"),
        _Link("https://shop.example/about"),
        _Link("https://shop.example/contact"),
    ]
    is_store, n = _looks_like_ecommerce(home, [])
    assert not is_store and n < ECOMMERCE_PRODUCT_URL_MIN   # under-detected up front

    # Subpages reveal the catalogue; the accumulated set crosses the threshold.
    accumulated = list(home) + [
        _Link(f"https://shop.example/products/p{i}") for i in range(ECOMMERCE_PRODUCT_URL_MIN)
    ]
    is_store2, n2 = _looks_like_ecommerce(accumulated, [])
    assert is_store2 and n2 >= ECOMMERCE_PRODUCT_URL_MIN


def test_mid_crawl_reevaluation_upgrades_page_cap_and_budget():
    """Mirror the crawl loop's H1 logic: start non-store on a thin homepage, then re-eval
    as each subpage adds links; the moment it flips, both the page cap AND the time budget
    rise (raising the cap alone is a measured no-op)."""
    home = [_Link("https://shop.example/products/a"), _Link("https://shop.example/help")]
    is_store, _ = _looks_like_ecommerce(home, [])
    page_cap, budget_secs = (
        (ECOMMERCE_MAX_INTERNAL_PAGES, ECOMMERCE_BUDGET_SECONDS) if is_store
        else (MAX_INTERNAL_PAGES, TOTAL_BUDGET_SECONDS)
    )
    assert (page_cap, budget_secs) == (MAX_INTERNAL_PAGES, TOTAL_BUDGET_SECONDS)

    accumulated = list(home)
    flipped_at = None
    for i in range(ECOMMERCE_PRODUCT_URL_MIN + 3):
        accumulated.append(_Link(f"https://shop.example/products/p{i}"))
        if not is_store:
            is_store, n_prod = _looks_like_ecommerce(accumulated, [])
            if is_store:
                page_cap, budget_secs = ECOMMERCE_MAX_INTERNAL_PAGES, ECOMMERCE_BUDGET_SECONDS
                flipped_at = i

    assert is_store and flipped_at is not None
    assert page_cap == ECOMMERCE_MAX_INTERNAL_PAGES
    assert budget_secs == ECOMMERCE_BUDGET_SECONDS
    assert ECOMMERCE_MAX_INTERNAL_PAGES > MAX_INTERNAL_PAGES         # deeper crawl
    assert ECOMMERCE_BUDGET_SECONDS > TOTAL_BUDGET_SECONDS           # more time


def test_non_store_stays_on_default_budget():
    """A genuine non-store (few product URLs even after accumulation) must NOT be upgraded
    — the wide frontier must not over-crawl an ordinary site."""
    links = [_Link(f"https://gov.example/{p}") for p in
             ("about", "contact", "programs", "news", "admissions", "faq", "team")]
    is_store, n = _looks_like_ecommerce(links, [])
    assert not is_store and n < ECOMMERCE_PRODUCT_URL_MIN
