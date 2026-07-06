"""Pickable products from the RAW scrape (dashboard/products.py).

The product-picker (owner/engineer suggestion #1) must offer REAL products the user can advertise,
grounded in the scraped data — not the profile's content_images (which turned out to be
store-location photos). This locks the extraction: names from real product/collection pages the
crawl reached, images from real on-site assets, chrome (banners/logos) excluded. Hermetic.
"""
from __future__ import annotations

from dashboard.products import products_from_manifest, _titleize


def test_titleize_cleans_shopify_slugs():
    assert _titleize("shop-hair-care") == "Hair Care"
    assert _titleize("hair-growth") == "Hair Growth"
    assert _titleize("b2g1-eid-offer") == "B2G1 Eid Offer"


def _manifest():
    return {
        "pages": [
            {"final_url": "https://b.com/", "page_type": "homepage"},
            {"final_url": "https://b.com/collections/hair-growth", "page_type": "products"},
            {"final_url": "https://b.com/collections/shop-face-care", "page_type": "products"},
            {"final_url": "https://b.com/pages/contact-us", "page_type": "contact"},
        ],
        "images_of_interest": [
            {"role": "logo", "src": "https://b.com/logo.png", "alt": "logo"},
            {"role": "content", "src": "https://b.com/hair-growth-oil.jpg", "alt": "hair growth oil"},
            {"role": "content", "src": "https://b.com/web_banner_1.webp", "alt": "banner slide"},
            {"role": "content", "src": "https://b.com/face-wash.jpg", "alt": "face wash"},
        ],
    }


def test_products_are_grounded_lines_with_real_images():
    prods = products_from_manifest(_manifest())
    names = [p["name"] for p in prods]
    assert "Hair Growth" in names and "Face Care" in names        # real product lines
    # non-product pages (home / contact) are NOT products
    assert not any(n.lower() in ("home", "contact", "contact us") for n in names)
    # name -> image match works, and chrome (banner/logo) is never offered as a product image
    hg = next(p for p in prods if p["name"] == "Hair Growth")
    assert "hair-growth" in hg["image"]
    for p in prods:
        img = p["image"].lower()
        assert "banner" not in img and "logo" not in img
        assert p["image"].startswith("http")


def test_no_product_pages_yields_empty():
    assert products_from_manifest({"pages": [{"final_url": "https://b.com/", "page_type": "homepage"}]}) == []
    assert products_from_manifest({}) == []
