"""Single-product-by-URL extraction (scraper.product_page.parse_product) — hermetic, no fetch.

The owner: give a direct product link for an item the crawl never reached -> scrape THAT page's
name / image / price. JSON-LD Product first, then og:/meta/<h1> fallback.
"""
from __future__ import annotations

from scraper.product_page import ProductInfo, parse_product


_JSONLD = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product",
 "name":"Rosemary Hair Growth Mist",
 "image":["https://shop.example/img/hairgrowth.jpg"],
 "description":"A lightweight rosemary mist that supports hair growth.",
 "offers":{"@type":"Offer","price":"250.00","priceCurrency":"EGP","availability":"InStock"}}
</script></head><body><h1>Some page heading</h1></body></html>
"""

_OG_ONLY = """
<html><head>
<meta property="og:title" content="Follicle Booster Oil"/>
<meta property="og:image" content="/img/oil.png"/>
<meta name="description" content="A booster oil for thicker hair."/>
</head><body><h1>Follicle Booster Oil</h1></body></html>
"""

_H1_ONLY = """
<html><head><title>Store</title></head>
<body><h1>Shea Butter Deep Mask</h1><img src="/img/mask.jpg"></body></html>
"""

_NOT_A_PRODUCT = """
<html><head><title>About us</title></head><body><p>We are a company.</p></body></html>
"""


def test_parse_product_from_jsonld():
    p = parse_product(_JSONLD, "https://shop.example/products/hair-growth")
    assert isinstance(p, ProductInfo) and p.usable
    assert p.name == "Rosemary Hair Growth Mist"
    assert p.image == "https://shop.example/img/hairgrowth.jpg"
    assert p.price == "250.00" and p.currency == "EGP"
    assert "rosemary" in p.description.lower()
    # JSON-LD name wins over the page's generic <h1>
    assert p.name != "Some page heading"


def test_parse_product_falls_back_to_og_and_resolves_relative_image():
    p = parse_product(_OG_ONLY, "https://shop.example/products/oil")
    assert p is not None and p.name == "Follicle Booster Oil"
    assert p.image == "https://shop.example/img/oil.png"     # /img/oil.png -> absolute
    assert "booster oil" in p.description.lower()


def test_parse_product_uses_h1_when_no_structured_name():
    p = parse_product(_H1_ONLY, "https://shop.example/products/mask")
    assert p is not None and p.name == "Shea Butter Deep Mask"


def test_non_product_page_returns_none():
    assert parse_product(_NOT_A_PRODUCT, "https://shop.example/about") is None


def test_blank_html_returns_none():
    assert parse_product("", "https://shop.example/x") is None
