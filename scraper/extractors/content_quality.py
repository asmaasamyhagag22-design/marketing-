"""Content quality extractor (PR-3).

Uses trafilatura to derive two signals per page:

  - `cleaned_main_text` — the article body with nav/footer/cookie-banner
    noise stripped. Useful for the LLM evidence-pack summary line and
    as a sanity check on the DOM walker. Persisted in the manifest so
    the build is reproducible (no need to re-import trafilatura at
    extraction time).

  - `has_meaningful_content` — True when the cleaned text is dense
    enough to feed a category/SWOT reasoning step. False means the
    page returned 200 OK but only carried scaffolding (cookies, nav,
    legal). The scraper-side `ScrapeDiagnostics.pages_with_text_blocks`
    count can then be honest about how many pages actually contributed
    information.

Design rules:
  - This module DOES NOT replace `scraper/extractors/text_blocks.py`.
    text_blocks runs in the browser via page.evaluate() and produces
    per-element evidence with bounding boxes — that's the validator's
    citation source. trafilatura runs on raw HTML in Python and produces
    one page-level paragraph stream. Both signals are kept.
  - Failures degrade gracefully. ImportError, parse errors, encoding
    issues, or empty input all return (None, False) — never raise.
  - Threshold values for `has_meaningful_content` are stored at module
    level so they can be tuned without touching call sites.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# A page's cleaned main text must clear ALL of these thresholds to be
# considered meaningful. Tuned conservatively — better to under-count
# than to count nav/cookie-only pages as "real content."
_MIN_CHARS = 120          # roughly 2-3 short sentences
_MIN_WORDS = 24           # filters out "Home / Menu / Contact" lists
_MIN_AVG_WORD_LEN = 3.0   # filters out one-letter menu link explosions


def extract_content_quality(html: str, page_url: str) -> tuple[Optional[str], bool]:
    """Run trafilatura on `html` and return (cleaned_main_text, has_meaningful_content).

    Returns (None, False) on:
      - empty/whitespace HTML
      - missing trafilatura (graceful degradation)
      - trafilatura returning None (its way of saying "no usable content")
      - any internal trafilatura exception

    Returns (text, True) when the cleaned text passes density thresholds.
    Returns (text, False) when trafilatura found *some* text but it
    didn't pass thresholds (e.g. nav-only / cookie-only pages). The text
    is still returned in this case so manifest readers can inspect it
    for debugging — but downstream consumers should respect the bool.
    """
    if not html or not html.strip():
        return (None, False)

    try:
        import trafilatura  # lazy import — keeps cold start cheap
    except ImportError:
        logger.info("trafilatura not installed; content quality skipped.")
        return (None, False)

    try:
        text = trafilatura.extract(
            html,
            url=page_url,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            favor_precision=True,   # prefer dropping cruft over keeping noise
        )
    except Exception as exc:
        # trafilatura can raise on encoding edge cases, malformed XML,
        # rare lxml issues. We must never break the scrape because of it.
        logger.warning("trafilatura failed on %s: %s", page_url, exc)
        return (None, False)

    if text is None:
        return (None, False)

    cleaned = text.strip()
    if not cleaned:
        return (None, False)

    return (cleaned, _is_meaningful(cleaned))


def _is_meaningful(text: str) -> bool:
    """Density gate. See module docstring for the thresholds."""
    if len(text) < _MIN_CHARS:
        return False
    words = text.split()
    if len(words) < _MIN_WORDS:
        return False
    avg_len = sum(len(w) for w in words) / len(words)
    if avg_len < _MIN_AVG_WORD_LEN:
        return False
    return True