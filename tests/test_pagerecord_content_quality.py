"""Tests for PageRecord's new cleaned_main_text + has_meaningful_content
fields (PR-3), and how they feed into ScrapeDiagnostics.
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
    PageRecord, PageType, PageTier, ReadinessReport, RobotsRecord,
    ScrapeManifest, ScrapeMeta, Section, SiteMetadata, TextBlock,
)


def _now():
    return datetime.now(timezone.utc)


def _make_page(
    url: str,
    *,
    cleaned: str | None = None,
    meaningful: bool = False,
    n_blocks: int = 0,
) -> PageRecord:
    blocks = [
        TextBlock(
            block_id=f"b{i}", page_url=url, section=Section.MAIN, tag="p",
            selector=f"p:nth-child({i})", text=f"Block {i}",
        )
        for i in range(n_blocks)
    ]
    return PageRecord(
        url=url, final_url=url, http_status=200,
        fetched_at=_now(), fetch_duration_ms=100,
        page_type=PageType.HOMEPAGE, tier=PageTier.HIGH,
        viewport_width=1366, viewport_height=800,
        text_blocks=blocks,
        cleaned_main_text=cleaned,
        has_meaningful_content=meaningful,
    )


def test_pagerecord_defaults_preserve_backward_compat():
    """A PageRecord built without the new fields must still work."""
    p = PageRecord(
        url="https://x.example/", final_url="https://x.example/",
        http_status=200, fetched_at=_now(), fetch_duration_ms=100,
        page_type=PageType.HOMEPAGE, tier=PageTier.HIGH,
        viewport_width=1366, viewport_height=800,
    )
    assert p.cleaned_main_text is None
    assert p.has_meaningful_content is False


def test_pagerecord_round_trips_via_json():
    p = _make_page(
        "https://x.example/about",
        cleaned="This is the cleaned main text of the about page.",
        meaningful=True,
    )
    raw = p.model_dump_json()
    reloaded = PageRecord.model_validate_json(raw)
    assert reloaded.cleaned_main_text == "This is the cleaned main text of the about page."
    assert reloaded.has_meaningful_content is True


def test_legacy_manifest_without_new_fields_still_loads():
    """JSON manifests written before PR-3 will lack cleaned_main_text +
    has_meaningful_content on PageRecord. Loading must succeed; defaults
    are None / False."""
    p = _make_page("https://x.example/")
    data = json.loads(p.model_dump_json())
    data.pop("cleaned_main_text", None)
    data.pop("has_meaningful_content", None)
    reloaded = PageRecord.model_validate(data)
    assert reloaded.cleaned_main_text is None
    assert reloaded.has_meaningful_content is False


# ---------------------------------------------------------------------
# ScrapeDiagnostics.pages_with_text_blocks now respects has_meaningful_content
# ---------------------------------------------------------------------

def _make_manifest(pages: list[PageRecord]) -> ScrapeManifest:
    return ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url="https://x.example/",
            normalized_url="https://x.example/",
            scraped_at=_now(),
            pages_attempted=len(pages),
            pages_succeeded=len(pages),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=ReadinessReport(
            has_homepage=True, has_internal_pages=True,
            has_contact_signals=False, has_visual_signals=False,
            has_cta_candidates=False, has_metadata=False,
            ready_for_extraction=True,
        ),
        site_metadata=SiteMetadata(),
        pages=pages,
    )


def test_pages_with_text_blocks_uses_meaningful_content_signal():
    """In the crawler's diagnostics block, the count of pages-with-real-
    text should prefer has_meaningful_content over a naive text_blocks check."""
    # Simulate what the crawler's _page_carries_real_text helper does
    def _page_carries_real_text(p):
        if getattr(p, "has_meaningful_content", False):
            return True
        if p.cleaned_main_text is None and p.text_blocks:
            return True
        return False

    pages = [
        # Page A: trafilatura says meaningful → counts
        _make_page("https://x.example/about", cleaned="Big article body", meaningful=True),
        # Page B: trafilatura says NOT meaningful (nav-only) → doesn't count
        _make_page("https://x.example/", cleaned="Home Menu Contact", meaningful=False),
        # Page C: legacy (no trafilatura run) but has text_blocks → counts via fallback
        _make_page("https://x.example/legacy", cleaned=None, meaningful=False, n_blocks=3),
    ]
    count = sum(1 for p in pages if _page_carries_real_text(p))
    assert count == 2  # A + C, not B