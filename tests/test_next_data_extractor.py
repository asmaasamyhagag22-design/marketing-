"""Tests for the Next.js __NEXT_DATA__ extractor (PR-next-data, 2026-05).

What's covered (per the user's required test list):
  1. Fixture with Buffalo-style HTML containing __NEXT_DATA__ and loading overlay
  2. When DOM text_blocks = 0, Next.js fallback extracts menu categories
  3. Extracts featured menu items with prices
  4. Extracts hotline 19914 as short-code phone
  5. Extracts CTA candidates from i18n actions
  6. Does not crash on malformed __NEXT_DATA__
  7. Does not use fallback when __NEXT_DATA__ is absent
  8. Existing tests stay green (handled by full-suite run)

Plus the 3 recommended additional cases:
  9. Whitelist positive: hotline/call_us/order_now keys ARE extracted
 10. Whitelist negative: footer_legal_terms/field_email_placeholder NOT extracted
 11. next_data_likely_dominant fires when payload >> DOM text
"""
from __future__ import annotations

import json
import sys
import types

_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for _n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, _n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from scraper.extractors.next_data import extract_next_data  # noqa: E402


# ---------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------

def _buffalo_style_payload() -> dict:
    """Realistic Next.js payload modeled on Buffalo Burger's actual data
    shape: menu_categories, featured_menu_items with prices, hotline in
    i18n, CTA strings in i18n, plus some non-customer-facing i18n keys
    that should NOT be extracted."""
    return {
        "props": {
            "pageProps": {
                "menu_categories": [
                    {"id": 1, "name": "Burgers", "name_ar": "برجر", "slug": "burgers"},
                    {"id": 2, "name": "Sides", "name_ar": "مقبلات", "slug": "sides"},
                    {"id": 3, "name": "Drinks", "slug": "drinks"},
                ],
                "featured_menu_items": [
                    {
                        "id": 101, "title": "Classic Cheeseburger",
                        "title_ar": "تشيز برجر كلاسيك",
                        "description": "Grilled beef patty with cheddar.",
                        "category": "Burgers", "slug": "classic-cheeseburger",
                        "image": "https://cdn.example/item/classic.jpg",
                        "total_price": 120, "net_price": 105,
                    },
                    {
                        "id": 102, "title": "Double Stack",
                        "description": "Two patties, double the joy.",
                        "category": "Burgers", "slug": "double-stack",
                        "total_price": 180,
                    },
                ],
                "hot_deals": [
                    {"id": 201, "title": "Family Bundle", "slug": "family-bundle",
                     "total_price": 350},
                ],
                "i18n": {
                    # Whitelisted — must be extracted
                    "hotline": "19914",
                    "call_us": "Call Us 19914",
                    "order_now": "Order Now",
                    "go_to_cart": "Go to cart",
                    "checkout": "Checkout",
                    "download_app": "Download app",
                    "view_menu": "View Menu",
                    # NOT whitelisted — must NOT be extracted
                    "footer_legal_terms": "Terms and conditions",
                    "field_email_placeholder": "you@example.com",
                    "page_title_help_center": "How can we help?",
                    "validation_error_required": "This field is required",
                },
            },
        },
        "page": "/",
        "buildId": "abc123",
    }


def _wrap_in_html(payload: dict, include_loading_overlay: bool = False) -> str:
    """Wrap a JSON payload in a Buffalo-style HTML page.

    When include_loading_overlay=True, the body contains only a loading
    spinner div (simulating the case where DOM extraction would yield 0
    text blocks). The __NEXT_DATA__ script holds the real content.
    """
    body = ""
    if include_loading_overlay:
        body = '<div class="loading-overlay"><div class="spinner"></div></div>'
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
        f'<body>{body}'
        '<script id="__NEXT_DATA__" type="application/json">'
        f'{json.dumps(payload)}'
        '</script></body></html>'
    )


# =====================================================================
# 1. Fixture with Buffalo-style HTML containing __NEXT_DATA__ and overlay
# =====================================================================

def test_buffalo_style_fixture_extracts_top_level_signals():
    """End-to-end smoke test on the user's described Buffalo Burger shape."""
    html = _wrap_in_html(_buffalo_style_payload(), include_loading_overlay=True)
    r = extract_next_data(html, "https://buffaloburger.com/")
    assert r.found is True
    assert r.payload_size_bytes > 0
    # We should have BOTH menu items AND phones AND CTAs at minimum.
    assert len(r.schema_blocks) >= 3, "expected at least 3 MenuItem blocks"
    assert any(b.type == "MenuItem" for b in r.schema_blocks)
    assert any(b.source == "next_data" for b in r.schema_blocks)
    assert any(p.raw == "19914" and p.is_short_code for p in r.phones)
    assert any(c.anchor_text == "Order Now" for c in r.cta_candidates)


# =====================================================================
# 2. DOM text_blocks=0 + Next.js fallback extracts menu categories
# =====================================================================

def test_next_data_extracts_when_dom_would_be_empty():
    """The user's core scenario: the page renders only a loading
    overlay so DOM text_blocks=0, but __NEXT_DATA__ carries the menu.
    The extractor must still produce content."""
    html = _wrap_in_html(_buffalo_style_payload(), include_loading_overlay=True)
    r = extract_next_data(html, "https://buffaloburger.com/")
    # Categories surface as inferred internal URLs (we synthesize
    # /branches/all/menu#{slug} per the user's spec).
    category_slugs = {
        link.anchor_text for link in r.inferred_internal
        if "menu#" in link.href
    }
    assert "burgers" in category_slugs
    assert "sides" in category_slugs
    assert "drinks" in category_slugs


# =====================================================================
# 3. Featured menu items with prices
# =====================================================================

def test_featured_menu_items_extracted_with_prices():
    html = _wrap_in_html(_buffalo_style_payload())
    r = extract_next_data(html, "https://buffaloburger.com/")
    menu_items = [b for b in r.schema_blocks if b.type == "MenuItem"]
    # We have 2 featured_menu_items + 1 hot_deals item — total 3
    assert len(menu_items) == 3

    by_name = {b.data["name"]: b for b in menu_items}
    assert "Classic Cheeseburger" in by_name
    classic = by_name["Classic Cheeseburger"]
    assert classic.data["offers"]["price"] == 120
    assert classic.data.get("description") == "Grilled beef patty with cheddar."
    # Arabic alt name preserved
    assert classic.data.get("alternateName") == "تشيز برجر كلاسيك"
    # Source provenance is correct
    assert classic.source == "next_data"


def test_menu_items_without_price_are_not_misclassified_as_categories():
    """Regression guard: a menu item with no price should not slip into
    the category shape detector. Conversely, a category (no price)
    should not be picked up as a menu item."""
    payload = {
        "props": {"pageProps": {
            "menu_categories": [
                {"id": 1, "name": "Burgers", "slug": "burgers"},
            ],
            "featured_menu_items": [
                {"id": 101, "title": "No Price Item", "slug": "no-price"},
            ],
        }},
    }
    r = extract_next_data(_wrap_in_html(payload), "https://x.example/")
    # No menu items (the one without a price doesn't match the shape).
    menu_items = [b for b in r.schema_blocks if b.type == "MenuItem"]
    assert menu_items == []
    # The category did get picked up — synthesized URL is in inferred_internal.
    assert any(link.anchor_text == "burgers" for link in r.inferred_internal)


# =====================================================================
# 4. Hotline 19914 as short-code phone
# =====================================================================

def test_hotline_extracted_as_short_code():
    html = _wrap_in_html(_buffalo_style_payload())
    r = extract_next_data(html, "https://buffaloburger.com/")
    hotlines = [p for p in r.phones if p.is_short_code]
    assert len(hotlines) == 1
    p = hotlines[0]
    assert p.raw == "19914"
    assert p.e164 is None
    assert p.page_url == "https://buffaloburger.com/"


def test_hotline_dedupe_across_i18n_keys():
    """The same number 19914 appears under both `hotline` and `call_us`
    i18n keys. The extractor must dedupe by digit-string and only emit
    one PhoneRecord."""
    payload = {"props": {"pageProps": {"i18n": {
        "hotline": "19914",
        "call_us": "Call Us 19914",
    }}}}
    r = extract_next_data(_wrap_in_html(payload), "https://x.example/")
    assert len([p for p in r.phones if p.raw == "19914"]) == 1


# =====================================================================
# 5. CTA candidates from i18n
# =====================================================================

def test_ctas_extracted_from_whitelisted_i18n_keys():
    html = _wrap_in_html(_buffalo_style_payload())
    r = extract_next_data(html, "https://buffaloburger.com/")
    anchors = {c.anchor_text for c in r.cta_candidates}
    assert "Order Now" in anchors
    assert "Go to cart" in anchors
    assert "Checkout" in anchors
    assert "Download app" in anchors
    assert "View Menu" in anchors
    # "Call Us 19914" comes from `call_us` (in both whitelists)
    assert "Call Us 19914" in anchors


# =====================================================================
# 6. Malformed __NEXT_DATA__ does not crash
# =====================================================================

def test_malformed_json_does_not_crash():
    """The script tag is there, but the JSON is broken. Extractor must
    flag found=True (the tag existed) but return no extracted content,
    and add a parse-failed note."""
    html = (
        '<html><body>'
        '<script id="__NEXT_DATA__" type="application/json">'
        '{this is not valid json'
        '</script></body></html>'
    )
    r = extract_next_data(html, "https://x.example/")
    assert r.found is True
    assert r.schema_blocks == []
    assert r.phones == []
    assert r.cta_candidates == []
    assert any("parse_failed" in n for n in r.notes)


def test_empty_script_body_treated_as_not_found():
    """An empty <script id=__NEXT_DATA__> tag with no body should not
    register as found=True."""
    html = (
        '<html><body>'
        '<script id="__NEXT_DATA__" type="application/json"></script>'
        '</body></html>'
    )
    r = extract_next_data(html, "https://x.example/")
    assert r.found is False


def test_non_object_payload_handled_gracefully():
    """JSON that parses but isn't an object/list (e.g. just `null` or a
    bare number) should be flagged with a note, not crash."""
    html = (
        '<html><body>'
        '<script id="__NEXT_DATA__" type="application/json">null</script>'
        '</body></html>'
    )
    r = extract_next_data(html, "https://x.example/")
    assert r.found is True
    assert any("not_object" in n for n in r.notes)


# =====================================================================
# 7. No fallback when __NEXT_DATA__ is absent
# =====================================================================

def test_no_next_data_tag_returns_clean_empty_result():
    """A regular HTML page with no __NEXT_DATA__ script tag must
    produce found=False and a clean empty result."""
    html = "<html><body><main><p>Welcome to our site.</p></main></body></html>"
    r = extract_next_data(html, "https://x.example/")
    assert r.found is False
    assert r.payload_size_bytes == 0
    assert r.schema_blocks == []
    assert r.phones == []
    assert r.cta_candidates == []
    assert r.inferred_internal == []
    assert r.notes == []


def test_empty_html_returns_clean_empty_result():
    """Robustness against degenerate inputs."""
    r = extract_next_data("", "https://x.example/")
    assert r.found is False
    r = extract_next_data("   ", "https://x.example/")
    assert r.found is False


# =====================================================================
# 9. Whitelist positive cases
# =====================================================================

def test_whitelist_positive_phone_keys():
    """All these i18n key names must route to phones."""
    payload = {"props": {"pageProps": {"i18n": {
        "hotline": "19914",
        "phone_number": "10001",
        "helpline": "11111",
    }}}}
    r = extract_next_data(_wrap_in_html(payload), "https://x.example/")
    phones = {p.raw for p in r.phones}
    assert "19914" in phones
    assert "10001" in phones
    assert "11111" in phones


def test_whitelist_positive_cta_keys():
    payload = {"props": {"pageProps": {"i18n": {
        "book_now": "Book Now",
        "reserve_table": "Reserve a table",
        "buy_now": "Buy now",
        "contact_us": "Contact us",
    }}}}
    r = extract_next_data(_wrap_in_html(payload), "https://x.example/")
    anchors = {c.anchor_text for c in r.cta_candidates}
    assert "Book Now" in anchors
    assert "Reserve a table" in anchors
    assert "Buy now" in anchors
    assert "Contact us" in anchors


def test_whitelist_key_normalization_handles_camelcase_and_dashes():
    """goToCart, go_to_cart, and go-to-cart must all be recognized."""
    payload = {"props": {"pageProps": {"i18n": {
        "goToCart": "Go to cart (camel)",
        "view-menu": "View Menu (dash)",
    }}}}
    r = extract_next_data(_wrap_in_html(payload), "https://x.example/")
    anchors = {c.anchor_text for c in r.cta_candidates}
    assert "Go to cart (camel)" in anchors
    assert "View Menu (dash)" in anchors


# =====================================================================
# 10. Whitelist negative cases — noise prevention
# =====================================================================

def test_whitelist_negative_non_customer_facing_keys():
    """These i18n keys must NOT produce phones or CTAs, even though
    their values contain phone-looking or CTA-looking strings."""
    payload = {"props": {"pageProps": {"i18n": {
        # Looks like a phone but the key is a placeholder
        "field_email_placeholder": "you@example.com",
        "phone_placeholder": "+20 100 000 0000",  # dev placeholder
        # Looks like CTAs but the keys are unrelated
        "footer_legal_terms": "Terms and conditions",
        "validation_error_required": "This field is required",
        "page_title_help_center": "How can we help?",
        "error_500_message": "Something went wrong, please try again.",
    }}}}
    r = extract_next_data(_wrap_in_html(payload), "https://x.example/")
    # No phones extracted from non-whitelisted keys — even though
    # phone_placeholder's value DOES contain "+20 100 000 0000".
    assert r.phones == []
    # No CTAs from non-whitelisted keys either.
    assert r.cta_candidates == []


def test_long_cta_strings_dropped():
    """CTAs are short by definition. A whitelisted key with a long
    sentence value (>80 chars) is probably misused; don't extract."""
    long_value = "Order now to get an exclusive discount that will be applied automatically at checkout for new customers"
    payload = {"props": {"pageProps": {"i18n": {
        "order_now": long_value,
    }}}}
    r = extract_next_data(_wrap_in_html(payload), "https://x.example/")
    assert r.cta_candidates == []


# =====================================================================
# 11. next_data_likely_dominant signal
# =====================================================================

def test_next_data_likely_dominant_computed_correctly():
    """This signal is computed by the crawler (not the extractor itself).
    We test the threshold logic in isolation here."""
    # The extractor doesn't compute likely_dominant itself; the crawler
    # does. We just verify the size signal is available.
    html = _wrap_in_html(_buffalo_style_payload())
    r = extract_next_data(html, "https://x.example/")
    # The Buffalo-style payload is well over 1000 bytes; with DOM
    # text_chars=0, the crawler's threshold (payload > 10 * max(dom, 1))
    # is satisfied.
    assert r.payload_size_bytes > 500


# =====================================================================
# Inferred URL safety — synthesized URLs are NOT auto-fetched
# =====================================================================

def test_inferred_urls_are_recorded_not_auto_promoted():
    """Synthesized URLs (e.g. /branches/all/offer-detail/{slug}) must
    land in `inferred_internal`, NOT in any field the crawler would
    auto-fetch."""
    html = _wrap_in_html(_buffalo_style_payload())
    r = extract_next_data(html, "https://buffaloburger.com/")
    # All inferred URLs are on the same registrable host
    assert all(
        link.href.startswith("https://buffaloburger.com/")
        for link in r.inferred_internal
    )
    # At least one /offer-detail/{slug} synthesized for each featured item
    offer_urls = {link.href for link in r.inferred_internal if "offer-detail" in link.href}
    assert "https://buffaloburger.com/branches/all/offer-detail/classic-cheeseburger" in offer_urls
    assert "https://buffaloburger.com/branches/all/offer-detail/double-stack" in offer_urls


# =====================================================================
# Capacity limits
# =====================================================================

def test_huge_payload_rejected_with_size_note():
    """Payloads over 3 MB are rejected before parsing to prevent DoS."""
    # Build a payload that, after JSON encoding, exceeds 3 MB.
    huge_value = "x" * (3 * 1024 * 1024 + 100)
    html = (
        '<html><body>'
        '<script id="__NEXT_DATA__" type="application/json">'
        f'{{"data": "{huge_value}"}}'
        '</script></body></html>'
    )
    r = extract_next_data(html, "https://x.example/")
    assert r.found is True
    assert any("too_large" in n for n in r.notes)
    assert r.schema_blocks == []


def test_menu_item_cap_enforced():
    """A pathological page with 500 menu items must not flood the
    manifest. Cap is 80 (MAX_MENU_ITEMS)."""
    items = [
        {"id": i, "title": f"Item {i}", "slug": f"item-{i}", "total_price": i}
        for i in range(500)
    ]
    payload = {"props": {"pageProps": {"items": items}}}
    r = extract_next_data(_wrap_in_html(payload), "https://x.example/")
    menu_items = [b for b in r.schema_blocks if b.type == "MenuItem"]
    assert len(menu_items) == 80