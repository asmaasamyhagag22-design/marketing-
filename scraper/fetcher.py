"""Page fetching via Playwright.

Responsibilities:
- Launch a Chromium browser context with our user agent and viewport.
- For a given URL, navigate, scroll to trigger lazy loading, capture
  HTML, two screenshots (full + viewport), and bot-protection signals.
- Return a `FetchResult` dataclass; the caller decides what to do
  with it (extract, classify, etc.).

This module knows nothing about the manifest or downstream stages.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, TimeoutError as PWTimeout
from playwright.sync_api import Error as PWError

from .config import (
    ACCEPT_LANGUAGE,
    BOT_PROTECTION_TEXT_SIGNALS,
    NAV_TIMEOUT_MS,
    PAGE_TIMEOUT_MS,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    USER_AGENT,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
)
from .errors import ErrorCode
from .time_utils import utc_now
from datetime import datetime


@dataclass
class FetchResult:
    url: str
    final_url: str
    http_status: Optional[int]
    fetched_at: datetime
    duration_ms: int
    html: str = ""
    rendered_text: str = ""
    full_screenshot_bytes: bytes = b""
    viewport_screenshot_bytes: bytes = b""
    content_hash: Optional[str] = None
    screenshot_hash: Optional[str] = None
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None
    bytes_downloaded: int = 0
    # True when navigation timed out but Playwright still exposed useful DOM.
    # The crawler should process the page and record the timeout as a warning
    # on PageRecord.failures instead of dropping the page completely.
    partial_content: bool = False
    partial_reason: Optional[str] = None
    # True when the (non-critical) full-page screenshot failed. The page still succeeds —
    # visual identity degrades gracefully to logo pixels + header/footer colors — so this
    # is surfaced as a manifest note, NOT an error_code that would discard the page.
    screenshot_failed: bool = False
    # Marker for the caller — used by extractors that need a live Page
    # for computed-CSS reads. We attach the Page only when requested.
    _page: Optional[Page] = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return self.error_code is None


def _finalize_hashes_and_bytes(result: FetchResult) -> None:
    if result.html:
        result.content_hash = hashlib.sha256(result.html.encode("utf-8", errors="replace")).hexdigest()
    if result.full_screenshot_bytes:
        result.screenshot_hash = hashlib.sha256(result.full_screenshot_bytes).hexdigest()
    result.bytes_downloaded = (
        len(result.html.encode("utf-8", errors="replace"))
        + len(result.full_screenshot_bytes)
        + len(result.viewport_screenshot_bytes)
    )


def _salvage_partial_dom(page: Page, result: FetchResult, reason: str) -> bool:
    """Best-effort DOM salvage after navigation timeout.

    Some real sites time out on network/lazy assets while the useful DOM is
    already present. Returning True here means the crawler can still extract
    text, links, menu content, and visual hints from the partially loaded page.
    """
    try:
        result.final_url = page.url or result.final_url
    except Exception:
        pass

    try:
        result.html = page.content() or ""
    except Exception:
        result.html = result.html or ""

    try:
        result.rendered_text = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
    except Exception:
        result.rendered_text = result.rendered_text or ""

    if not (result.html.strip() or result.rendered_text.strip()):
        return False

    try:
        result.full_screenshot_bytes = page.screenshot(full_page=True, type="png")
    except Exception:
        pass

    try:
        result.viewport_screenshot_bytes = page.screenshot(full_page=False, type="png")
    except Exception:
        pass

    result.partial_content = True
    result.partial_reason = f"timeout_partial_content_salvaged: {reason[:220]}"
    _finalize_hashes_and_bytes(result)
    return True


def make_browser_context(browser: Browser) -> BrowserContext:
    """Create a context with our standard fingerprint."""
    return browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        java_script_enabled=True,
        ignore_https_errors=False,
        locale="en-US",
        extra_http_headers={"Accept-Language": ACCEPT_LANGUAGE},
    )


def _capture_screenshots(page: Page, result: FetchResult) -> None:
    """Capture the full-page + viewport screenshots for a FULL homepage fetch.

    A screenshot failure is NON-FATAL: the page's html/text/links/offerings are already
    captured and ARE the core of the profile, and visual identity degrades gracefully to
    logo pixels + header/footer colors when no screenshot exists. Setting an error_code
    here made result.ok False and DISCARDED the whole fully-scraped page (MEASURED:
    azzafahmy.com -> 0 pages on a SCREENSHOT_FAILED, losing all its text/offerings). We flag
    the degradation (surfaced as a manifest note) instead of failing the page."""
    try:
        result.full_screenshot_bytes = page.screenshot(full_page=True, type="png")
    except PWError as e:
        result.screenshot_failed = True
        result.error_message = f"full_page screenshot failed (non-fatal): {str(e)[:180]}"
    try:
        result.viewport_screenshot_bytes = page.screenshot(full_page=False, type="png")
    except PWError:
        # Viewport screenshot is non-critical; skip silently.
        pass


def _detect_bot_protection(text: str, title: str) -> Optional[ErrorCode]:
    haystack = (text[:5000] + " " + (title or "")).lower()
    if "captcha" in haystack:
        return ErrorCode.CAPTCHA_DETECTED
    for sig in BOT_PROTECTION_TEXT_SIGNALS:
        if sig in haystack:
            # "just a moment" + cloudflare-style screen
            return ErrorCode.BOT_PROTECTION
    return None


def _scroll_to_load(page: Page) -> None:
    """Scroll through the page to trigger lazy-loaded content, DWELLING at the
    bottom so async footer widgets finish before we capture the DOM.

    MEASURED (elkbabgi.com, a Strikingly site): the footer social links are
    injected by JS only after the footer has been in view for ~1s. The old
    fast scroll (120ms/step, then immediately back to top) captured the DOM
    before the widget rendered -> social/logo silently dropped. We now scroll to
    a stable bottom, dwell, and wait for network to settle before capturing.
    Universal (helps any lazy-loading site), not site-specific.
    """
    try:
        page.evaluate(
            """async () => {
                const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                let last = -1;
                for (let i = 0; i < 40; i++) {
                    window.scrollBy(0, Math.max(400, window.innerHeight * 0.9));
                    await sleep(250);
                    const reached = window.scrollY + window.innerHeight;
                    const h = document.body.scrollHeight;
                    if (reached >= h - 5) {
                        if (h === last) break;     // stable bottom reached
                        last = h;                  // grew (lazy content) -> keep going
                    }
                }
                await sleep(1400);                 // dwell for lazy footer widgets
                window.scrollTo(0, 0);
                await sleep(250);
            }"""
        )
        # Late XHR-driven widgets (e.g. a social-icons footer) need a final beat.
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except PWTimeout:
            pass
    except PWError:
        # Best-effort; not fatal
        pass


# Transient failures worth a retry: a network blip, an HTTP/2 reset, or a
# navigation timeout often clears on a second try. Permanent outcomes
# (bot-block, CAPTCHA, 4xx, empty DOM) are NOT retried — retrying them just
# wastes the scrape budget and can look like hammering.
_TRANSIENT_ERRORS = {
    ErrorCode.NETWORK_ERROR,
    ErrorCode.RENDER_ERROR,
    ErrorCode.TIMEOUT,
}


# Heavy, non-essential resource types blocked on LIGHT sub-page fetches: sub-pages are crawled
# for TEXT + LINKS (+ DOM-based image URLs, which are attributes, not loaded pixels), so loading
# images/media/fonts only burns time. Scripts / XHR / CSS / documents still load, so JS-injected
# content (products, links, lazy text) is preserved. Universal (helps any heavy page).
_HEAVY_RESOURCE_TYPES = frozenset({"image", "media", "font"})


def _block_heavy_route(route) -> None:
    try:
        if route.request.resource_type in _HEAVY_RESOURCE_TYPES:
            route.abort()
        else:
            route.continue_()
    except Exception:
        try:
            route.continue_()
        except Exception:
            pass


def fetch_page(context: BrowserContext, url: str, keep_page: bool = False,
               light: bool = False) -> FetchResult:
    """Fetch one page, retrying ONLY transient transport failures.

    A successful or permanently-failed result returns immediately. A transient
    failure (DNS/HTTP2/timeout) is retried up to RETRY_ATTEMPTS times with linear
    backoff. A failed attempt always closes its own page (see _fetch_page_once's
    finally), so retries never leak a page; only a successful keep_page result
    holds the live Page open for the caller.
    """
    result = _fetch_page_once(context, url, keep_page=keep_page, light=light)
    attempt = 0
    while (not result.ok
           and result.error_code in _TRANSIENT_ERRORS
           and attempt < RETRY_ATTEMPTS):
        attempt += 1
        time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        result = _fetch_page_once(context, url, keep_page=keep_page, light=light)
    if attempt and result.error_message:
        result.error_message = f"[retry {attempt}/{RETRY_ATTEMPTS}] {result.error_message}"
    return result


def _fetch_page_once(context: BrowserContext, url: str, keep_page: bool = False,
                     light: bool = False) -> FetchResult:
    """Fetch one page (single attempt). Caller is responsible for the context
    lifecycle.

    `light=True` (sub-page mode): block heavy resources (images/media/fonts) and skip the
    full-page screenshot — sub-pages need text + links, not pixels. Big render-time saving on
    image-heavy e-commerce; scripts/XHR/CSS still load so JS content is preserved.

    If keep_page=True, the returned FetchResult carries the live Page
    so extractors can run page.evaluate(). Caller MUST close the page
    after use (`result._page.close()`).
    """
    started = time.monotonic()
    result = FetchResult(
        url=url,
        final_url=url,
        http_status=None,
        fetched_at=utc_now(),
        duration_ms=0,
    )

    page = context.new_page()
    page.set_default_timeout(PAGE_TIMEOUT_MS)
    page.set_default_navigation_timeout(NAV_TIMEOUT_MS)
    if light:
        try:
            page.route("**/*", _block_heavy_route)
        except Exception:
            pass

    try:
        response = page.goto(url, wait_until="domcontentloaded")
        if response is not None:
            result.http_status = response.status
        result.final_url = page.url

        # Wait briefly for additional content; networkidle can hang forever
        # on sites with long-poll connections, so we cap it.
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except PWTimeout:
            pass

        # Trigger lazy content
        _scroll_to_load(page)

        # Grab HTML + text + title
        result.html = page.content()
        result.rendered_text = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
        title = page.title() or ""

        # Bot protection check
        bot_code = _detect_bot_protection(result.rendered_text, title)
        if bot_code is not None:
            result.error_code = bot_code
            result.error_message = f"Bot protection detected (title='{title[:80]}')"

        # Empty DOM check (after possible bot detection)
        elif not result.rendered_text.strip() and "<body" not in result.html.lower():
            result.error_code = ErrorCode.EMPTY_RENDERED_DOM
            result.error_message = "Rendered DOM has no body or visible text"

        elif not light:
            # Screenshots — only when content is real, and only for FULL fetches. The homepage
            # needs them for visual identity; LIGHT sub-pages skip them (pixels aren't used, and
            # the full-page screenshot is the slowest step + can hang on font loads).
            _capture_screenshots(page, result)

        # HTTP status flag (don't fail hard on 4xx — record but continue)
        if result.http_status and result.http_status >= 400 and result.error_code is None:
            result.error_code = ErrorCode.HTTP_ERROR
            result.error_message = f"HTTP {result.http_status}"

        _finalize_hashes_and_bytes(result)

    except PWTimeout as e:
        msg = str(e)[:300]
        if _salvage_partial_dom(page, result, msg):
            # Treat as processable content, but preserve the warning details.
            result.error_code = None
            result.error_message = result.partial_reason
        else:
            result.error_code = ErrorCode.TIMEOUT
            result.error_message = msg
    except PWError as e:
        msg = str(e).lower()
        if "net::err_name_not_resolved" in msg or "dns" in msg:
            result.error_code = ErrorCode.NETWORK_ERROR
        elif "ssl" in msg or "cert" in msg:
            result.error_code = ErrorCode.NETWORK_ERROR
        else:
            result.error_code = ErrorCode.RENDER_ERROR
        result.error_message = str(e)[:300]
    except Exception as e:
        result.error_code = ErrorCode.UNKNOWN_ERROR
        result.error_message = f"{type(e).__name__}: {e}"[:300]
    finally:
        result.duration_ms = int((time.monotonic() - started) * 1000)
        if keep_page and result.ok:
            result._page = page
        else:
            try:
                page.close()
            except Exception:
                pass

    return result
