"""Pickable products from the RAW scrape (dashboard/products.py).

The product-picker (owner/engineer suggestion #1) must offer REAL products the user can advertise,
grounded in the scraped data — not the profile's content_images (which turned out to be
store-location photos). This locks the extraction: names from real product/collection pages the
crawl reached, images from real on-site assets, chrome (banners/logos) excluded. Hermetic.
"""
from __future__ import annotations

import json

from dashboard.products import products_from_manifest, scrape_qa_for_slug, _titleize


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


def test_scrape_qa_summarizes_the_freshest_manifest(tmp_path):
    # a saved scrape under scrapes/<slug>_<ts>/manifest.json -> a compact quality summary the
    # Scraper-QA panel renders (so the owner can verify the scraper at a glance).
    m = _manifest()
    m["scrape_meta"] = {"final_url": "https://b.com/", "pages_attempted": 6,
                        "pages_succeeded": 5, "duration_ms": 42000, "budget_exceeded": False}
    m["readiness"] = {"ready_for_extraction": True, "major_missing": []}
    m["notes"] = ["E-commerce detected (12+ product URLs)",
                  "ajax_modal_details(https://b.com/cat): +6 JS-built detail URLs",
                  "some unrelated note"]
    m["failures"] = []
    m["pages"][1]["text_blocks"] = [{"text": "a"}, {"text": "b"}]
    d = tmp_path / "acme_20260706_120000"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps(m), encoding="utf-8")

    qa = scrape_qa_for_slug("acme", scrapes_dir=str(tmp_path))
    assert qa is not None
    assert qa["pages_succeeded"] == 5 and qa["pages_attempted"] == 6
    assert qa["ready"] is True and qa["products"] >= 2
    assert qa["text_blocks"] == 2 and qa["images"] == 4
    # only the notable notes are surfaced; the ajax lines AGGREGATE into one human summary
    # (owner 2026-07-12: stacked raw-URL rows were a visual mess), raw lines kept separately
    assert any("JS-modal detail pages resolved: +6 URLs" in n for n in qa["key_notes"])
    assert not any("ajax_modal_details(" in n for n in qa["key_notes"])
    assert qa["ajax_detail_lines"] and "b.com/cat" in qa["ajax_detail_lines"][0]
    assert not any("unrelated" in n for n in qa["key_notes"])


def test_scrape_qa_none_when_no_manifest(tmp_path):
    assert scrape_qa_for_slug("nobody", scrapes_dir=str(tmp_path)) is None


def test_save_product_scrape_writes_grounded_snapshot(tmp_path):
    # OWNER FEATURE: generating an ad for a picked product drops product_scrape_<product>.json
    # into the brand's scrape dir — pages/images/offerings that matched, so the owner sees how
    # far the crawl reached for THAT product.
    from dashboard.products import save_product_scrape
    m = _manifest()
    m["pages"][1]["text_blocks"] = [{"text": "Hair Growth Oil nourishes roots"},
                                    {"text": "unrelated block"}]
    d = tmp_path / "acme_20260706_120000"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    (d / "business_profile.json").write_text(json.dumps({
        "offerings": [{"name": "Hair Growth Oil", "price_text": "EGP 250",
                       "page_url": "https://b.com/collections/hair-growth"},
                      {"name": "Face Wash", "price_text": None, "page_url": None}],
    }), encoding="utf-8")

    out = save_product_scrape("acme", "Hair Growth", product_image="https://b.com/hair-growth-oil.jpg",
                              kind="poster", scrapes_dir=str(tmp_path))
    assert out is not None and out.parent == d and out.name == "product_scrape_hair-growth.json"
    snap = json.loads(out.read_text(encoding="utf-8"))
    assert snap["coverage"]["reached_product_page"] is True          # /collections/hair-growth
    assert snap["coverage"]["text_blocks_mentioning_product"] == 1   # one real mention
    assert snap["coverage"]["priced_offering_found"] is True         # EGP 250
    assert snap["offerings_matched"][0]["price_text"] == "EGP 250"
    assert any("hair-growth" in p["url"] for p in snap["pages_matched"])
    assert all(im["src"].startswith("http") for im in snap["images_matched"])
    assert snap["generation"]["kind"] == "poster"


def test_save_product_scrape_none_when_no_scrape(tmp_path):
    from dashboard.products import save_product_scrape
    assert save_product_scrape("nobody", "Anything", scrapes_dir=str(tmp_path)) is None


def test_best_image_grounds_by_page_association_not_random(tmp_path):
    # FIX-R3 (op-shoes): Arabic name + Shopify hash filenames -> word match impossible.
    # An image found ON the item's own page wins; with no grounded match the image is
    # EMPTY (honest) — never "the next unused sneaker".
    from dashboard.products import _best_image
    images = [
        {"src": "https://cdn/x-0cfc.png", "alt": "", "page": "https://s.com/collections/shoes"},
        {"src": "https://cdn/y-d413.jpg", "alt": "", "page": "https://s.com/collections/bags"},
    ]
    used: set = set()
    assert _best_image("الحقائب", images, used,
                       "https://s.com/collections/bags") == "https://cdn/y-d413.jpg"
    assert _best_image("الأحذية", images, used,
                       "https://s.com/collections/shoes") == "https://cdn/x-0cfc.png"
    # no page match + no word match -> EMPTY, not a random leftover
    assert _best_image("عطور", images, set(), "https://s.com/collections/perfume") == ""
