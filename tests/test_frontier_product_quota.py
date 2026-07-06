"""Frontier prefers INDIVIDUAL product pages (scraper coverage Slices 3-4).

The crawl fetched ~26 of 226 discovered pages and they were all COLLECTIONS — individual products
never reached — because /collections/rings and /products/<slug> classify identically, so the stable
sort let collections (discovered first) fill every slot. Now the frontier distinguishes product
pages (`is_product_detail`) and reserves a DIVERSE quota for them, so a store's catalogue is captured
item-by-item at the SAME page count. Hermetic.
"""
from __future__ import annotations

from scraper.classify.page_type import is_product_detail
from scraper.crawler import _reserve_product_quota
from scraper.schemas import PageTier, PageType


def _c(url):
    return (url, PageType.PRODUCTS, PageTier.HIGH, "")


def test_is_product_detail_distinguishes_pdp_from_collection():
    assert is_product_detail("https://b/products/gold-ring-42")
    assert is_product_detail("https://b/collections/rings/products/x")
    assert is_product_detail("https://b/pdp/sku-9")
    assert not is_product_detail("https://b/products")            # bare list
    assert not is_product_detail("https://b/collections/rings")   # a category/PLP
    assert not is_product_detail("https://b/products?page=2")      # paginated list


def test_frontier_reserves_a_diverse_spread_of_products():
    cands = [_c("https://b/collections/rings"), _c("https://b/about"), _c("https://b/contact")]
    for coll in ("rings", "necklaces", "studs"):          # products across THREE collections
        for i in range(15):
            cands.append(_c(f"https://b/collections/{coll}/products/item-{i}"))
    out = _reserve_product_quota(cands, 30)
    prods = [u for u, *_ in out if is_product_detail(u)]
    parents = {"/".join(u.split("/")[:-1]) for u in prods}
    assert len(out) == 30                                  # budget filled
    assert len(prods) >= 20                                # products DOMINATE (not collections)
    assert len(parents) == 3                               # spread across ALL collections, not one family
    assert any(not is_product_detail(u) for u, *_ in out)  # a landing/collection page still kept


def test_no_product_pages_leaves_frontier_unchanged():
    cands = [_c("https://b/about"), _c("https://b/contact"), _c("https://b/services")]
    assert _reserve_product_quota(cands, 2) == cands[:2]   # non-store: identical to the old behaviour
    assert _reserve_product_quota(cands, 0) == []
