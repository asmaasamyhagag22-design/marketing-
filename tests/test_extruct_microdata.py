"""Tests for Microdata extraction via extruct (PR-2).

Confirms:
- Microdata blocks are extracted and tagged with source="microdata"
- Restaurant / Dentist / Store / Product schema.org types are recognized
- Nested PostalAddress is preserved
- Items with no useful content are filtered out
- @type values arrive bare (no schema.org IRI prefix)
- The block's `data` field is shape-compatible with the existing
  from_schema_org walker (so a Microdata-only site gets category for free)
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

from scraper.extractors.structured_data import extract_structured_data  # noqa: E402


# ---------------------------------------------------------------------
# Basic Microdata
# ---------------------------------------------------------------------

def test_microdata_restaurant_extracted():
    html = """
    <html><body>
    <div itemscope itemtype="https://schema.org/Restaurant">
      <h1 itemprop="name">Andrea Restaurant</h1>
      <span itemprop="telephone">+201001234567</span>
      <span itemprop="servesCuisine">Egyptian</span>
    </div>
    </body></html>
    """
    blocks = extract_structured_data(html, "https://andrea.example/")
    assert len(blocks) == 1
    b = blocks[0]
    assert b.source == "microdata"
    assert b.type == "Restaurant"
    assert b.data["name"] == "Andrea Restaurant"
    assert b.data["telephone"] == "+201001234567"
    assert b.data["servesCuisine"] == "Egyptian"


def test_microdata_strips_schema_namespace_from_type():
    """@type values must come out as bare schema.org names so the
    existing from_schema_org category table matches them."""
    html = """
    <div itemscope itemtype="https://schema.org/Dentist">
      <span itemprop="name">Smile Clinic</span>
    </div>
    """
    blocks = extract_structured_data(html, "https://x.example/")
    assert len(blocks) == 1
    assert blocks[0].type == "Dentist"
    # And the embedded @type in data is also bare (matters for walker)
    assert blocks[0].data["@type"] == "Dentist"


def test_microdata_nested_address_preserved():
    html = """
    <div itemscope itemtype="https://schema.org/Restaurant">
      <h1 itemprop="name">Andrea</h1>
      <div itemprop="address" itemscope itemtype="https://schema.org/PostalAddress">
        <span itemprop="streetAddress">5 El Maryouteya</span>
        <span itemprop="addressLocality">Cairo</span>
      </div>
    </div>
    """
    blocks = extract_structured_data(html, "https://x.example/")
    assert len(blocks) == 1
    b = blocks[0]
    assert b.data["name"] == "Andrea"
    addr = b.data.get("address")
    assert isinstance(addr, dict)
    assert addr["streetAddress"] == "5 El Maryouteya"
    assert addr["addressLocality"] == "Cairo"


def test_microdata_multiple_items():
    """A page with multiple itemscope blocks yields multiple SchemaOrgBlocks."""
    html = """
    <div itemscope itemtype="https://schema.org/Organization">
      <span itemprop="name">EduCo</span>
    </div>
    <div itemscope itemtype="https://schema.org/Course">
      <span itemprop="name">Intro to Python</span>
    </div>
    """
    blocks = extract_structured_data(html, "https://x.example/")
    types = {b.type for b in blocks}
    assert "Organization" in types
    assert "Course" in types


def test_microdata_product_with_offer():
    """Common e-commerce pattern."""
    html = """
    <div itemscope itemtype="https://schema.org/Product">
      <span itemprop="name">Hydrating Serum</span>
      <span itemprop="brand">Sasco</span>
    </div>
    """
    blocks = extract_structured_data(html, "https://x.example/")
    assert any(b.type == "Product" for b in blocks)
    p = next(b for b in blocks if b.type == "Product")
    assert p.data["name"] == "Hydrating Serum"
    assert p.data["brand"] == "Sasco"


def test_microdata_no_useful_content_dropped():
    """An itemscope with only structural markup (no values) is dropped."""
    html = '<div itemscope itemtype="https://schema.org/Thing"></div>'
    blocks = extract_structured_data(html, "https://x.example/")
    assert blocks == []


# ---------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------

def test_empty_html_returns_empty():
    assert extract_structured_data("", "https://x.example/") == []
    assert extract_structured_data("   ", "https://x.example/") == []


def test_html_with_no_microdata_returns_empty():
    """A normal HTML page with no structured markup just returns []."""
    html = "<html><body><h1>Hello world</h1><p>Some text.</p></body></html>"
    blocks = extract_structured_data(html, "https://x.example/")
    assert blocks == []


def test_malformed_html_does_not_crash():
    """extruct + lxml must tolerate broken HTML without raising."""
    # extruct is built on lxml which is permissive; this should not raise
    blocks = extract_structured_data("<<<not real html>>>", "https://x.example/")
    assert blocks == []


# ---------------------------------------------------------------------
# Walker-compatibility test (the architectural win of PR-2)
# ---------------------------------------------------------------------

def test_microdata_block_feeds_existing_category_walker():
    """The whole point of PR-2: a Microdata-marked site should feed
    `from_schema_org` and produce a category, without modifying that
    module."""
    from datetime import datetime, timezone
    from business_profile.rules.from_schema_org import extract_category_from_schema_org
    from business_profile.schemas import BusinessCategory
    from scraper.schemas import (
        ReadinessReport, RobotsRecord, ScrapeManifest,
        ScrapeMeta, SiteMetadata,
    )

    html = """
    <div itemscope itemtype="https://schema.org/Restaurant">
      <h1 itemprop="name">Andrea Restaurant</h1>
    </div>
    """
    blocks = extract_structured_data(html, "https://andrea.example/")
    manifest = ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url="https://andrea.example/",
            normalized_url="https://andrea.example/",
            scraped_at=datetime.now(timezone.utc),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=ReadinessReport(
            has_homepage=True, has_internal_pages=False,
            has_contact_signals=False, has_visual_signals=False,
            has_cta_candidates=False, has_metadata=True,
            ready_for_extraction=False,
        ),
        site_metadata=SiteMetadata(schema_org=blocks),
    )
    category_field = extract_category_from_schema_org(manifest)
    assert category_field.value == BusinessCategory.RESTAURANT