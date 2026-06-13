"""Tests for RDFa extraction via extruct (PR-2).

RDFa is normalized so its output looks like JSON-LD / Microdata:
- Keys lose the `https://schema.org/` prefix
- `[{"@value": v}]` values are unwrapped to plain values
- Blank-node identifiers (_:N…) are dropped
- usesVocabulary noise nodes are dropped
- @type values are bare (not full IRIs)

This normalization is what lets RDFa-only sites be picked up by the
existing `from_schema_org.py` walker without changing that module.
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
# Basic RDFa
# ---------------------------------------------------------------------

def test_rdfa_dentist_extracted_and_normalized():
    html = """
    <html><body vocab="https://schema.org/" typeof="Dentist">
      <h1 property="name">Smile Clinic</h1>
      <span property="telephone">+201234567</span>
    </body></html>
    """
    blocks = extract_structured_data(html, "https://smile.example/")
    rdfa_blocks = [b for b in blocks if b.source == "rdfa"]
    assert len(rdfa_blocks) == 1
    b = rdfa_blocks[0]
    assert b.type == "Dentist"
    # Keys stripped of namespace
    assert b.data["name"] == "Smile Clinic"
    assert b.data["telephone"] == "+201234567"
    # @type is bare (matters for walker)
    assert b.data["@type"] == "Dentist"


def test_rdfa_drops_blank_node_id():
    """RDFa output for inline typeof has a `@id` like `_:Nabc123`. We must
    drop that since it's a blank-node anchor with no info."""
    html = """
    <body vocab="https://schema.org/" typeof="Restaurant">
      <span property="name">Andrea</span>
    </body>
    """
    blocks = extract_structured_data(html, "https://x.example/")
    rdfa = [b for b in blocks if b.source == "rdfa"]
    assert len(rdfa) == 1
    assert "@id" not in rdfa[0].data or not rdfa[0].data["@id"].startswith("_:")


def test_rdfa_drops_uses_vocabulary_noise():
    """The `usesVocabulary` node is RDFa structural cruft. We must drop it,
    not emit it as a SchemaOrgBlock."""
    html = """
    <body vocab="https://schema.org/" typeof="Restaurant">
      <span property="name">Andrea</span>
    </body>
    """
    blocks = extract_structured_data(html, "https://x.example/")
    # No block should have the usesVocabulary key in its data
    for b in blocks:
        for k in b.data.keys():
            assert "usesVocabulary" not in k


def test_rdfa_nested_address_flattens_to_separate_block():
    """extruct flattens RDFa graphs — a nested PostalAddress becomes a
    separate top-level block. That's a structural difference from JSON-LD
    but the walker iterates ALL blocks so category detection still works."""
    html = """
    <body vocab="https://schema.org/" typeof="Restaurant">
      <span property="name">Andrea</span>
      <div property="address" typeof="PostalAddress">
        <span property="streetAddress">5 El Maryouteya</span>
        <span property="addressLocality">Cairo</span>
      </div>
    </body>
    """
    blocks = extract_structured_data(html, "https://x.example/")
    rdfa = [b for b in blocks if b.source == "rdfa"]
    types = {b.type for b in rdfa}
    assert "Restaurant" in types
    assert "PostalAddress" in types
    addr_block = next(b for b in rdfa if b.type == "PostalAddress")
    assert addr_block.data["streetAddress"] == "5 El Maryouteya"
    assert addr_block.data["addressLocality"] == "Cairo"


# ---------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------

def test_rdfa_no_markup_returns_empty():
    html = "<html><body><p>No structured markup here.</p></body></html>"
    blocks = extract_structured_data(html, "https://x.example/")
    rdfa = [b for b in blocks if b.source == "rdfa"]
    assert rdfa == []


# ---------------------------------------------------------------------
# Walker-compatibility test (the architectural win of PR-2)
# ---------------------------------------------------------------------

def test_rdfa_block_feeds_existing_category_walker():
    """A site marked up ONLY with RDFa should produce a category via
    the existing from_schema_org walker without modification to that
    module."""
    from datetime import datetime, timezone
    from business_profile.rules.from_schema_org import extract_category_from_schema_org
    from business_profile.schemas import BusinessCategory
    from scraper.schemas import (
        ReadinessReport, RobotsRecord, ScrapeManifest,
        ScrapeMeta, SiteMetadata,
    )

    html = """
    <html><body vocab="https://schema.org/" typeof="Dentist">
      <h1 property="name">Smile Clinic</h1>
    </body></html>
    """
    blocks = extract_structured_data(html, "https://smile.example/")
    manifest = ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url="https://smile.example/",
            normalized_url="https://smile.example/",
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
    assert category_field.value == BusinessCategory.CLINIC