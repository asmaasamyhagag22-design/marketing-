"""Tests for ScrapeDiagnostics population on the manifest.

We don't run a live Playwright scrape here (that needs a browser). We
test the schema-level contract:
- Manifest field exists and accepts the new model
- Round-trips cleanly through JSON
- Older manifests without the field still load
- Default values are sensible

Integration with the real crawl loop is exercised in
test_crawler_uses_sitemap.py + test_sitemap_parsing.py.
"""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone

_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for _n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, _n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from scraper.schemas import (  # noqa: E402
    RobotsRecord, ScrapeDiagnostics, ScrapeManifest, ScrapeMeta,
)
from scraper.schemas import ReadinessReport as ScraperReadiness  # noqa: E402


def _now():
    return datetime.now(timezone.utc)


def _empty_readiness() -> ScraperReadiness:
    return ScraperReadiness(
        has_homepage=False, has_internal_pages=False,
        has_contact_signals=False, has_visual_signals=False,
        has_cta_candidates=False, has_metadata=False,
        ready_for_extraction=False,
    )


def test_default_diagnostics_values_are_safe():
    """A freshly-built ScrapeDiagnostics with no args must be valid
    and represent the 'nothing happened yet' state."""
    d = ScrapeDiagnostics()
    assert d.pages_discovered == 0
    assert d.pages_scraped == 0
    assert d.pages_with_text_blocks == 0
    assert d.pages_failed == 0
    assert d.sitemap_used is False
    assert d.sitemap_urls_found == 0
    # js_rendering_used defaults to True since the current crawler
    # always uses Playwright; future-proofs for a static fallback.
    assert d.js_rendering_used is True


def test_diagnostics_attaches_to_manifest():
    manifest = ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url="https://x.com/", normalized_url="https://x.com/",
            scraped_at=_now(),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=_empty_readiness(),
        scrape_diagnostics=ScrapeDiagnostics(
            pages_discovered=5, pages_scraped=3,
            sitemap_used=True, sitemap_urls_found=12,
        ),
    )
    assert manifest.scrape_diagnostics is not None
    assert manifest.scrape_diagnostics.pages_discovered == 5
    assert manifest.scrape_diagnostics.sitemap_used is True


def test_legacy_manifest_without_diagnostics_loads():
    """JSON manifests written before PR-1 will lack `scrape_diagnostics`.
    Loading must succeed and the field must be None."""
    legacy = ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url="https://x.com/", normalized_url="https://x.com/",
            scraped_at=_now(),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=_empty_readiness(),
    )
    raw_json = legacy.model_dump_json()
    # Round-trip — and additionally simulate a legacy file by stripping the field
    data = json.loads(raw_json)
    data.pop("scrape_diagnostics", None)
    reloaded = ScrapeManifest.model_validate(data)
    assert reloaded.scrape_diagnostics is None


def test_diagnostics_round_trips_via_json():
    manifest = ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url="https://x.com/", normalized_url="https://x.com/",
            scraped_at=_now(),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=_empty_readiness(),
        scrape_diagnostics=ScrapeDiagnostics(
            pages_discovered=8, pages_scraped=6,
            pages_with_text_blocks=5, pages_failed=2,
            sitemap_used=True, sitemap_urls_found=42,
            js_rendering_used=True,
        ),
    )
    raw = manifest.model_dump_json()
    reloaded = ScrapeManifest.model_validate_json(raw)
    assert reloaded.scrape_diagnostics is not None
    assert reloaded.scrape_diagnostics.pages_discovered == 8
    assert reloaded.scrape_diagnostics.sitemap_urls_found == 42


def test_robots_record_sitemap_urls_round_trips():
    """The PR-1 addition to RobotsRecord must also serialize cleanly."""
    r = RobotsRecord(
        checked=True, allowed=True,
        sitemap_urls=["https://x.com/sitemap.xml", "https://x.com/sitemap-2.xml"],
    )
    raw = r.model_dump_json()
    reloaded = RobotsRecord.model_validate_json(raw)
    assert reloaded.sitemap_urls == [
        "https://x.com/sitemap.xml", "https://x.com/sitemap-2.xml",
    ]


def test_robots_record_sitemap_urls_default_empty():
    """Without sitemap_urls in input, the default is an empty list (not None)."""
    r = RobotsRecord(checked=True, allowed=True)
    assert r.sitemap_urls == []