"""A blocked/empty scrape must fail loudly, not silently build a garbage dashboard.

Origin (2026-07-06 owner run + proactive audit): marasimltd.com's crawl returned 0 pages (expired
cert, then HTTP 403). full_run would still build a hollow profile + competitors + SWOT and write a
result that LOOKS successful, so the studio showed an empty/garbage dashboard instead of a clear
"couldn't read this site" message. Hermetic: a fake manifest, no network.
"""
from __future__ import annotations

from competitor.full_run import scrape_yielded_nothing


class _Manifest:
    def __init__(self, pages):
        self.pages = pages


def test_zero_page_crawl_is_detected_as_nothing():
    assert scrape_yielded_nothing(_Manifest([])) is True
    assert scrape_yielded_nothing(_Manifest(None)) is True


def test_a_crawl_with_pages_is_usable():
    assert scrape_yielded_nothing(_Manifest([object()])) is False
    assert scrape_yielded_nothing(_Manifest([object(), object()])) is False
