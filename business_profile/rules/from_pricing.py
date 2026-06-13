"""Pricing visibility detector.

Checks every text block across every page for currency mentions. The key
safety rule: absence of extracted price text is not the same as proof that the
business has no prices. Restaurant menu pages often render prices inside
images/PDFs/canvas widgets or time out before all content appears, so those
cases stay unknown with a diagnostic note.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from scraper.errors import ErrorCode
from scraper.schemas import PageType, ScrapeManifest, TextBlock

from ..schemas import (
    Confidence,
    EvidenceItem,
    EvidencedField,
    SourceType,
)


# Two patterns: currency-then-number, and number-then-currency.
# Includes EN, AR (Egyptian, Saudi, UAE, Kuwait), and major Western currencies.
_CURRENCY_THEN_NUMBER = re.compile(
    r"(?:[$€£¥₹]"
    r"|\b(?:EGP|USD|EUR|GBP|SAR|AED|KWD|JPY|INR|LE)\b"
    r"|L\.E\.|ج\.م|جنيه|ريال|درهم|دينار)"
    r"\s*\d",
    re.UNICODE | re.IGNORECASE,
)
_NUMBER_THEN_CURRENCY = re.compile(
    r"\d[\d,]*(?:\.\d{1,2})?\s*"
    r"(?:[$€£¥₹]"
    r"|\b(?:EGP|USD|EUR|GBP|SAR|AED|KWD|JPY|INR|LE)\b"
    r"|L\.E\.|ج\.م|جنيه|ريال|درهم|دينار)",
    re.UNICODE | re.IGNORECASE,
)

# Page types where price mentions are most credible (vs. e.g. blog posts)
_RELEVANT_PAGE_TYPES = {
    PageType.PRICING, PageType.PRODUCTS, PageType.SERVICES,
    PageType.MENU, PageType.BOOKING, PageType.HOMEPAGE,
}
_MENU_PATH_HINTS = ("menu", "menus", "food", "dishes", "meals", "منيو", "قائمة")


def _has_currency(text: str) -> bool:
    if not text:
        return False
    return bool(_CURRENCY_THEN_NUMBER.search(text) or _NUMBER_THEN_CURRENCY.search(text))


def _looks_like_menu_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        path = urlparse(url).path.lower()
    except Exception:
        path = str(url).lower()
    return any(h in path for h in _MENU_PATH_HINTS)


def _menu_pages(manifest: ScrapeManifest):
    return [
        p for p in manifest.pages
        if p.page_type == PageType.MENU or _looks_like_menu_url(p.final_url) or _looks_like_menu_url(p.url)
    ]


def _menu_failures(manifest: ScrapeManifest):
    failures = []
    for f in manifest.failures:
        if _looks_like_menu_url(f.page_url):
            failures.append(f)
    for p in manifest.pages:
        for f in p.failures:
            if p.page_type == PageType.MENU or _looks_like_menu_url(p.final_url) or _looks_like_menu_url(p.url):
                failures.append(f)
    return failures


def pricing_extraction_note(manifest: ScrapeManifest) -> str | None:
    """Return a short diagnostic code when pricing should remain unknown."""
    menus = _menu_pages(manifest)
    menu_failures = _menu_failures(manifest)

    if any(f.code == ErrorCode.TIMEOUT for f in menu_failures):
        return "menu_page_timeout_partial_or_failed"

    if menus:
        menu_blocks = [b for p in menus for b in p.text_blocks]
        if menu_blocks and not any(_has_currency(b.text) for b in menu_blocks):
            return "menu_page_found_but_prices_not_text_extracted"
        if not menu_blocks:
            return "menu_page_found_but_no_text_blocks"

    if menu_failures:
        return "menu_page_fetch_failed_or_not_processed"

    return None


def extract_pricing_visible(manifest: ScrapeManifest) -> EvidencedField[bool]:
    """True if at least 1 currency-with-number block exists on a
    relevant page; missing if unknown; False only when we have enough relevant
    non-menu text to confidently say no visible prices were found.
    """
    matches: list[TextBlock] = []
    examined = 0
    examined_on_relevant = 0
    examined_on_relevant_non_menu = 0

    for page in manifest.pages:
        is_relevant = page.page_type in _RELEVANT_PAGE_TYPES
        is_menu = page.page_type == PageType.MENU or _looks_like_menu_url(page.final_url) or _looks_like_menu_url(page.url)
        for block in page.text_blocks:
            examined += 1
            if is_relevant:
                examined_on_relevant += 1
                if not is_menu:
                    examined_on_relevant_non_menu += 1
            if _has_currency(block.text):
                if is_relevant:
                    matches.append(block)

    if matches:
        # Cap evidence at 3 to keep the profile readable
        evidence = [
            EvidenceItem(
                block_id=m.block_id,
                page_url=m.page_url,
                quote=m.text[:200],
                extractor="rule:currency_pattern",
            )
            for m in matches[:3]
        ]
        return EvidencedField(
            value=True,
            evidence=evidence,
            confidence=Confidence.HIGH if len(matches) >= 2 else Confidence.MEDIUM,
            source_type=SourceType.EXTRACTED,
        )

    # Critical restaurant/menu safety behavior: a menu page with no extracted
    # price text means unknown, not false. Prices may be image/PDF/canvas based.
    if pricing_extraction_note(manifest):
        return EvidencedField.missing()

    if examined_on_relevant_non_menu >= 80:
        # We looked at meaningful non-menu pages and saw no pricing. This is
        # still conservative and avoids using a menu timeout as negative proof.
        home_url = manifest.scrape_meta.final_url or manifest.scrape_meta.normalized_url
        return EvidencedField(
            value=False,
            evidence=[EvidenceItem(
                block_id=None,
                page_url=home_url,
                quote=None,
                extractor=f"rule:no_currency_in_{examined_on_relevant}_blocks",
            )],
            confidence=Confidence.HIGH if examined_on_relevant_non_menu >= 150 else Confidence.MEDIUM,
            source_type=SourceType.EXTRACTED,
        )

    # Too few relevant blocks to be confident either way.
    return EvidencedField.missing()
