"""Adaptive e-commerce crawl budget — universal detection (Pillar 1), hermetic, no network.

`_looks_like_ecommerce` flips ON only when the homepage links + sitemap reveal many PRODUCTS-type
URLs (via the existing page-type classifier — a SIGNAL, not a vertical/name). It dedups and
early-exits at the threshold.
"""
from __future__ import annotations

from scraper.config import ECOMMERCE_PRODUCT_URL_MIN
from scraper.crawler import _looks_like_ecommerce


class _Link:
    def __init__(self, href):
        self.href = href


def test_store_detected_by_product_url_density():
    sitemap = [f"https://shop.example/products/item-{i}" for i in range(ECOMMERCE_PRODUCT_URL_MIN + 5)]
    is_store, n = _looks_like_ecommerce([], sitemap)
    assert is_store and n >= ECOMMERCE_PRODUCT_URL_MIN


def test_non_store_not_detected():
    links = [_Link("https://gov.example/about"), _Link("https://gov.example/contact"),
             _Link("https://gov.example/programs"), _Link("https://gov.example/news"),
             _Link("https://gov.example/admissions")]
    sitemap = ["https://gov.example/page-1", "https://gov.example/faq"]
    is_store, n = _looks_like_ecommerce(links, sitemap)
    assert not is_store


def test_dedups_homepage_and_sitemap_urls():
    # the SAME product URL in both homepage links and sitemap counts once
    prods = [f"https://s.example/products/p{i}" for i in range(ECOMMERCE_PRODUCT_URL_MIN + 3)]
    links = [_Link(u) for u in prods]
    is_store, _ = _looks_like_ecommerce(links, list(prods))  # identical set duplicated
    assert is_store  # still detected (the distinct count exceeds the threshold)

    few = [f"https://s.example/products/p{i}" for i in range(3)]
    is_store2, n2 = _looks_like_ecommerce([_Link(u) for u in few], list(few))
    assert not is_store2 and n2 == 3  # 3 distinct products, dedup'd across both inputs
