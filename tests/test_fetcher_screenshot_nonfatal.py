"""Gate: a full-page screenshot failure must NOT discard a fully-scraped page.

Regression origin (2026-07-05 audit of the logo/palette pipeline): the full-page
screenshot runs AFTER html/text/links are captured, but its failure set
error_code=SCREENSHOT_FAILED, which makes result.ok False, which made the crawler drop the
whole homepage (MEASURED: azzafahmy.com -> 0 pages, losing all its text/offerings). The
screenshot is non-critical — visual identity degrades gracefully to logo pixels +
header/footer colors — so the failure is a flag/note, not a fatal error.

Hermetic: fake page objects, no Playwright/browser.
"""
from datetime import datetime, timezone

from scraper.fetcher import _capture_screenshots, FetchResult, PWError


def _result():
    return FetchResult(url="https://x.example/", final_url="https://x.example/",
                       http_status=200, fetched_at=datetime.now(timezone.utc), duration_ms=100,
                       html="<html><body>real content</body></html>", rendered_text="real content")


class _Page:
    """Fake page: full_page screenshot fails, viewport succeeds (or per flags)."""
    def __init__(self, full_ok=True, viewport_ok=True):
        self.full_ok, self.viewport_ok = full_ok, viewport_ok

    def screenshot(self, *, full_page, type):  # noqa: A002 - mirrors Playwright's kwarg
        ok = self.full_ok if full_page else self.viewport_ok
        if not ok:
            raise PWError("screenshot timed out")
        return b"PNGDATA" if full_page else b"VPDATA"


def test_full_screenshot_failure_keeps_page_ok():
    r = _result()
    _capture_screenshots(_Page(full_ok=False, viewport_ok=True), r)
    assert r.ok is True                 # the page survives (was discarded before)
    assert r.error_code is None
    assert r.screenshot_failed is True
    assert r.full_screenshot_bytes == b""
    assert r.viewport_screenshot_bytes == b"VPDATA"   # viewport still captured


def test_both_screenshots_failing_still_keeps_page_ok():
    r = _result()
    _capture_screenshots(_Page(full_ok=False, viewport_ok=False), r)
    assert r.ok is True and r.screenshot_failed is True


def test_successful_screenshots_do_not_flag_failure():
    r = _result()
    _capture_screenshots(_Page(full_ok=True, viewport_ok=True), r)
    assert r.ok is True and r.screenshot_failed is False
    assert r.full_screenshot_bytes == b"PNGDATA"
