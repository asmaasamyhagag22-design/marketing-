
"""Tests for cross-source dedupe (PR-2).

Some sites emit BOTH JSON-LD and Microdata for the same business —
typically as belt-and-braces SEO. Without dedupe, we'd see two blocks
for what is conceptually the same entity, which would inflate
schema.org-derived counts and could confuse downstream category
detection if the two blocks disagreed.

The dedupe rule (see scraper/extractors/structured_data.py):
- Two blocks are duplicates when they share (type, name).
- On collision, json_ld > microdata > rdfa.

We also test the merge_metadata-side dedupe (PR-2 extended that path so
homepage+contact-page-emitted-the-same-block doesn't produce two).
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

from scraper.extractors.metadata import extract_metadata, merge_metadata  # noqa: E402
from scraper.extractors.structured_data import dedupe_schema_blocks  # noqa: E402
from scraper.schemas import SchemaOrgBlock, SiteMetadata  # noqa: E402


# ---------------------------------------------------------------------
# dedupe_schema_blocks unit tests
# ---------------------------------------------------------------------

def test_dedupe_keeps_jsonld_over_microdata():
    blocks = [
        SchemaOrgBlock(type="Restaurant", data={"name": "Andrea"}, source="json_ld"),
        SchemaOrgBlock(type="Restaurant", data={"name": "Andrea"}, source="microdata"),
    ]
    out = dedupe_schema_blocks(blocks)
    assert len(out) == 1
    assert out[0].source == "json_ld"


def test_dedupe_keeps_microdata_over_rdfa():
    blocks = [
        SchemaOrgBlock(type="Dentist", data={"name": "Smile"}, source="rdfa"),
        SchemaOrgBlock(type="Dentist", data={"name": "Smile"}, source="microdata"),
    ]
    out = dedupe_schema_blocks(blocks)
    assert len(out) == 1
    assert out[0].source == "microdata"


def test_dedupe_keeps_distinct_names_as_separate_blocks():
    blocks = [
        SchemaOrgBlock(type="Restaurant", data={"name": "Andrea"}, source="json_ld"),
        SchemaOrgBlock(type="Restaurant", data={"name": "Sequoia"}, source="microdata"),
    ]
    out = dedupe_schema_blocks(blocks)
    assert len(out) == 2


def test_dedupe_keeps_distinct_types_as_separate_blocks():
    """Same name, different type → genuinely different entities (e.g. an
    Organization and an Event both branded with the same name)."""
    blocks = [
        SchemaOrgBlock(type="Organization", data={"name": "Andrea"}, source="json_ld"),
        SchemaOrgBlock(type="Restaurant", data={"name": "Andrea"}, source="json_ld"),
    ]
    out = dedupe_schema_blocks(blocks)
    assert len(out) == 2


def test_dedupe_name_match_is_case_insensitive():
    blocks = [
        SchemaOrgBlock(type="Restaurant", data={"name": "Andrea"}, source="json_ld"),
        SchemaOrgBlock(type="Restaurant", data={"name": "ANDREA"}, source="microdata"),
    ]
    out = dedupe_schema_blocks(blocks)
    assert len(out) == 1


def test_dedupe_preserves_untyped_unnameable_blocks():
    """A block with neither type nor name can't be deduped — keep it."""
    blocks = [
        SchemaOrgBlock(type=None, data={"unknownField": "x"}, source="json_ld"),
        SchemaOrgBlock(type=None, data={"unknownField": "y"}, source="microdata"),
    ]
    out = dedupe_schema_blocks(blocks)
    assert len(out) == 2


# ---------------------------------------------------------------------
# Integration: extract_metadata dedupes when the same site emits both
# ---------------------------------------------------------------------

def test_extract_metadata_dedupes_jsonld_and_microdata_for_same_business():
    """A real SEO pattern: emit a JSON-LD Restaurant block AND a
    Microdata-marked Restaurant block for the same business. We must
    end up with one block, not two."""
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Restaurant","name":"Andrea Restaurant","telephone":"+201001234567"}
        </script>
      </head>
      <body>
        <div itemscope itemtype="https://schema.org/Restaurant">
          <h1 itemprop="name">Andrea Restaurant</h1>
          <span itemprop="telephone">+201001234567</span>
        </div>
      </body>
    </html>
    """
    metadata = extract_metadata(html, "https://andrea.example/")
    # We expect exactly ONE Restaurant block, and it should be the JSON-LD one
    restaurant_blocks = [b for b in metadata.schema_org if b.type == "Restaurant"]
    assert len(restaurant_blocks) == 1
    assert restaurant_blocks[0].source == "json_ld"


def test_extract_metadata_sources_jsonld_blocks_correctly_tagged():
    """Existing JSON-LD blocks must now carry source='json_ld' explicitly."""
    html = """
    <html><head>
      <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Restaurant","name":"Andrea"}
      </script>
    </head></html>
    """
    metadata = extract_metadata(html, "https://x.example/")
    assert len(metadata.schema_org) == 1
    assert metadata.schema_org[0].source == "json_ld"


def test_extract_metadata_pure_microdata_site():
    """A site with ONLY Microdata, no JSON-LD → block tagged microdata."""
    html = """
    <html><body>
      <div itemscope itemtype="https://schema.org/Restaurant">
        <h1 itemprop="name">Andrea</h1>
      </div>
    </body></html>
    """
    metadata = extract_metadata(html, "https://x.example/")
    restaurant_blocks = [b for b in metadata.schema_org if b.type == "Restaurant"]
    assert len(restaurant_blocks) == 1
    assert restaurant_blocks[0].source == "microdata"


def test_extract_metadata_handles_mixed_block_types():
    """A site with JSON-LD Organization + Microdata Product (different
    types, different entities) should keep both."""
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Organization","name":"Sasco"}
        </script>
      </head>
      <body>
        <div itemscope itemtype="https://schema.org/Product">
          <span itemprop="name">Hydrating Serum</span>
        </div>
      </body>
    </html>
    """
    metadata = extract_metadata(html, "https://x.example/")
    types_and_sources = {(b.type, b.source) for b in metadata.schema_org}
    assert ("Organization", "json_ld") in types_and_sources
    assert ("Product", "microdata") in types_and_sources


# ---------------------------------------------------------------------
# Integration: merge_metadata dedupes when two pages produce the same block
# ---------------------------------------------------------------------

def test_merge_metadata_dedupes_repeated_blocks():
    """If both homepage and contact page emit the same Restaurant
    block, the merged metadata should not contain it twice."""
    homepage = SiteMetadata(
        title="Andrea Restaurant",
        schema_org=[
            SchemaOrgBlock(
                type="Restaurant", source="json_ld",
                data={"@context": "https://schema.org", "@type": "Restaurant", "name": "Andrea"},
            ),
        ],
    )
    contact = SiteMetadata(
        schema_org=[
            SchemaOrgBlock(
                type="Restaurant", source="json_ld",
                data={"@context": "https://schema.org", "@type": "Restaurant", "name": "Andrea"},
            ),
        ],
    )
    merged = merge_metadata(homepage, contact)
    assert len(merged.schema_org) == 1


def test_merge_metadata_keeps_distinct_blocks_from_different_pages():
    """Homepage carries the Organization block, /menu carries a Product
    block — merge should keep both."""
    homepage = SiteMetadata(
        schema_org=[
            SchemaOrgBlock(type="Organization", source="json_ld", data={"name": "Sasco"}),
        ],
    )
    menu_page = SiteMetadata(
        schema_org=[
            SchemaOrgBlock(type="Product", source="microdata", data={"name": "Serum"}),
        ],
    )
    merged = merge_metadata(homepage, menu_page)
    types = {b.type for b in merged.schema_org}
    assert types == {"Organization", "Product"}