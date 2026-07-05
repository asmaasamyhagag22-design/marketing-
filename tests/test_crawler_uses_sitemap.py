"""Tests for the crawler's URL-queue builder with sitemap URLs.

Asserts that _select_subpages_to_fetch:
- accepts an extra_urls list (sitemap-discovered URLs)
- classifies each via the same classify_url() pipeline
- dedupes against homepage links by normalized URL
- prefers homepage anchor text on collisions
- filters out cross-host sitemap entries
- filters out SKIP-tier sitemap entries (e.g. blog detail pages)
"""
from __future__ import annotations

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

from scraper.crawler import _select_subpages_to_fetch  # noqa: E402
from scraper.schemas import LinkCategory, LinkRecord  # noqa: E402


SITE = "https://example.com/"
HOME = "https://example.com/"


def _link(href: str, anchor: str = "", category=LinkCategory.INTERNAL) -> LinkRecord:
    return LinkRecord(
        href=href, anchor_text=anchor, page_url=HOME, category=category,
    )


# ---------------------------------------------------------------------
# Basic behavior
# ---------------------------------------------------------------------

def test_no_extra_urls_behaves_identically_to_baseline():
    """When extra_urls is omitted or empty, the function behaves exactly
    as it did before PR-1 (regression guard for the existing tests)."""
    home_links = [
        _link("https://example.com/menu", "Menu"),
        _link("https://example.com/about", "About us"),
    ]
    out_a = _select_subpages_to_fetch(home_links, SITE, HOME)
    out_b = _select_subpages_to_fetch(home_links, SITE, HOME, extra_urls=[])
    out_c = _select_subpages_to_fetch(home_links, SITE, HOME, extra_urls=None)
    assert out_a == out_b == out_c
    assert {row[0] for row in out_a} == {
        "https://example.com/menu",
        "https://example.com/about",
    }


def test_sitemap_urls_are_added_to_queue():
    home_links = [_link("https://example.com/about", "About us")]
    extra = ["https://example.com/menu", "https://example.com/contact"]
    out = _select_subpages_to_fetch(home_links, SITE, HOME, extra_urls=extra)
    urls = {row[0] for row in out}
    assert "https://example.com/about" in urls
    assert "https://example.com/menu" in urls
    assert "https://example.com/contact" in urls


def test_homepage_link_wins_anchor_text_on_collision():
    """If the same URL appears in both homepage links AND extra_urls,
    keep the homepage entry's anchor text (more signal)."""
    home_links = [_link("https://example.com/menu", "View Our Menu")]
    extra = ["https://example.com/menu"]  # collision
    out = _select_subpages_to_fetch(home_links, SITE, HOME, extra_urls=extra)
    # Exactly one entry, with the homepage anchor preserved
    menu_rows = [r for r in out if r[0] == "https://example.com/menu"]
    assert len(menu_rows) == 1
    assert menu_rows[0][3] == "View Our Menu"


def test_sitemap_trailing_slash_variant_collapses_to_homepage_entry():
    """H3 (changed 2026-07-05): a trailing-slash variant of a page already discovered
    via homepage links is the SAME logical page and must NOT get its own frontier slot.
    Previously /menu and /menu/ were kept as two distinct queue entries and each burned
    a budget fetch (MEASURED: orange.eg fetched http+https and slash variants of the same
    page). The frontier now dedups on the scheme/slash-insensitive `dedup_key`, keeping
    ONE entry (the homepage form + its richer anchor); the fetch url stays faithful."""
    home_links = [_link("https://example.com/menu", "Menu")]
    extra = ["https://example.com/menu/"]  # trailing-slash variant of the same page
    out = _select_subpages_to_fetch(home_links, SITE, HOME, extra_urls=extra)
    menu_rows = [r for r in out if r[0].rstrip("/") == "https://example.com/menu"]
    assert len(menu_rows) == 1                 # collapsed, not two slots
    assert menu_rows[0][0] == "https://example.com/menu"   # homepage form kept as fetch url
    assert menu_rows[0][3] == "Menu"           # homepage anchor preserved on the collision


# ---------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------

def test_sitemap_urls_filtered_by_same_host():
    home_links = [_link("https://example.com/about", "About")]
    extra = [
        "https://example.com/menu",
        "https://other-site.com/menu",   # cross-host: must be rejected
    ]
    out = _select_subpages_to_fetch(home_links, SITE, HOME, extra_urls=extra)
    urls = {row[0] for row in out}
    assert "https://example.com/menu" in urls
    assert all("other-site.com" not in u for u in urls)


def test_sitemap_homepage_url_itself_is_filtered():
    """A sitemap entry for the homepage must not duplicate the homepage."""
    home_links = []
    extra = [HOME, "https://example.com/contact"]
    out = _select_subpages_to_fetch(home_links, SITE, HOME, extra_urls=extra)
    urls = {row[0] for row in out}
    assert HOME not in urls
    assert "https://example.com/contact" in urls


def test_sitemap_skip_tier_pages_are_dropped():
    """Blog DETAIL URLs are SKIP tier per page_type classification.
    A sitemap full of /news/2024-01-01-some-post entries should not
    fill the crawler queue."""
    home_links = [_link("https://example.com/about", "About")]
    extra = [
        "https://example.com/news/2024-01-01-launch",      # SKIP
        "https://example.com/blog/2024/02/01/post-detail", # SKIP
        "https://example.com/menu",                         # HIGH
    ]
    out = _select_subpages_to_fetch(home_links, SITE, HOME, extra_urls=extra)
    urls = {row[0] for row in out}
    assert "https://example.com/menu" in urls
    # The skipped ones must not appear
    assert "https://example.com/news/2024-01-01-launch" not in urls
    assert "https://example.com/blog/2024/02/01/post-detail" not in urls