"""Cross-page dedup in build_inventory (social + cta_candidates).

The crawl emits one LinkRecord per (page, link), so a site-wide nav/footer link
is repeated once per crawled page. build_inventory collapses those repeats,
first-occurrence-wins:
  - social keyed on normalize_url(href).rstrip("/")
  - cta    keyed on (normalize_url(href).rstrip("/"), anchor_text)
Other buckets (internal/external/contact_protocol) are left untouched.

Locks in the matrix-reader fix at its source. Benchmarked against real manifests:
thehairaddict social 7->1 / cta 14->2; assih social 51->14; laser cta 14->1.
"""
from __future__ import annotations

import sys
import types

# Stub playwright so scraper.schemas imports cleanly in this env.
_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from scraper.schemas import LinkCategory, LinkRecord  # noqa: E402
from scraper.extractors.links import build_inventory  # noqa: E402


def _social(href, page, platform="whatsapp"):
    return LinkRecord(href=href, anchor_text="Chat", page_url=page,
                      category=LinkCategory.SOCIAL, platform=platform)


def _cta(href, anchor, page):
    return LinkRecord(href=href, anchor_text=anchor, page_url=page,
                      category=LinkCategory.CTA)


def test_social_same_href_across_pages_collapses_first_wins():
    href = "https://wa.me/201092001443"
    links = [_social(href, f"https://x.com/p{i}") for i in range(7)]
    inv = build_inventory(links)
    assert len(inv.social) == 1
    # first occurrence wins -> provenance points at the first page seen
    assert inv.social[0].page_url == "https://x.com/p0"


def test_social_trailing_slash_and_tracking_param_variants_collapse():
    # /x and /x/ are the same; an fbclid-decorated WhatsApp URL is the same number
    links = [
        _social("https://api.whatsapp.com/send?phone=2010", "https://x.com/a"),
        _social("https://api.whatsapp.com/send?phone=2010&fbclid=ABC", "https://x.com/b"),
        _social("https://x.com/page", "https://x.com/a"),
        _social("https://x.com/page/", "https://x.com/b"),
    ]
    inv = build_inventory(links)
    assert len(inv.social) == 2


def test_cta_same_href_same_anchor_collapses_but_distinct_anchor_survives():
    home = "https://x.com/"
    links = [
        _cta(home + "contact-us", "Contact Us", home),
        _cta(home + "contact-us/", "Contact Us", home + "p1"),   # trailing-slash dup
        _cta(home + "contact-us", "Get in touch", home + "p2"),  # distinct anchor, same href
    ]
    inv = build_inventory(links)
    assert len(inv.cta_candidates) == 2
    assert {c.anchor_text for c in inv.cta_candidates} == {"Contact Us", "Get in touch"}


def test_other_buckets_untouched_and_cta_still_surfaced_in_internal():
    home = "https://x.com/"
    # two identical CTAs across pages + an internal + an external
    links = [
        _cta(home + "book", "Book", home),
        _cta(home + "book", "Book", home + "p1"),
        LinkRecord(href=home + "about", anchor_text="About", page_url=home,
                   category=LinkCategory.INTERNAL),
        LinkRecord(href="https://other.com", anchor_text="Ext", page_url=home,
                   category=LinkCategory.EXTERNAL),
    ]
    inv = build_inventory(links)
    # cta_candidates deduped to 1...
    assert len(inv.cta_candidates) == 1
    # ...but internal keeps BOTH CTA appends (unconditional) + the real internal
    assert len(inv.internal) == 3
    assert len(inv.external) == 1
