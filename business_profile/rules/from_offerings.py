"""Small rule-based offering fallback for restaurants/cafés.

This is intentionally narrow. It does not replace the LLM offerings extractor;
it only prevents obvious restaurant pages from producing zero offerings when the
menu/about/home copy already contains clear cuisine/menu/service-mode evidence.
"""
from __future__ import annotations

import re

from scraper.schemas import PageType, ScrapeManifest, TextBlock

from ..schemas import Confidence, EvidenceItem, Offering

_RESTAURANT_PAGE_TYPES = {
    PageType.HOMEPAGE,
    PageType.ABOUT,
    PageType.MENU,
    PageType.CATERING,
    PageType.DELIVERY_ORDER,
    PageType.OFFERS,
}

_RESTAURANT_SIGNALS = re.compile(
    r"\b(restaurant|cafe|café|cuisine|menu|dish|dishes|food|meal|meals|grill|grilled|kebab|kabab|kofta|stew|stews|dining|takeaway|delivery|catering)\b"
    r"|مطعم|كافيه|منيو|قائمة|طعام|أكل|مشويات|كباب|وجبات|توصيل|ضيافة",
    re.IGNORECASE | re.UNICODE,
)

# Identity-level tokens for the gate below. Deliberately EXCLUDES the generic
# words that caused measured false fires on non-restaurants: menu/قائمة (every
# Arabic site's nav is "القائمة الرئيسية" = "main menu"), food/طعام,
# delivery/توصيل + "order online" (any e-commerce), meals.
_STRONG_IDENTITY_TOKENS: dict[str, re.Pattern[str]] = {
    name: re.compile(rx, re.IGNORECASE | re.UNICODE)
    for name, rx in {
        "restaurant": r"\brestaurants?\b", "مطعم": r"مطعم|مطاعم",
        "cafe": r"\bcaf[eé]s?\b", "كافيه": r"كافيه",
        "cuisine": r"\bcuisines?\b",
        "kebab": r"\bkebab|kabab\b", "كباب": r"كباب",
        "kofta": r"\bkofta\b", "كفتة": r"كفتة",
        "grill": r"\bgrill(?:ed|s)?\b", "مشويات": r"مشويات",
        "dish": r"\bdish(?:es)?\b", "أطباق": r"أطباق",
        "dining": r"\bdining\b",
        "tagine": r"\btagines?\b", "molokhia": r"\bmolokhia\b", "ملوخية": r"ملوخية",
        "chef": r"\bchefs?\b", "شيف": r"شيف",
    }.items()
}


def _passes_restaurant_gate(manifest: ScrapeManifest) -> bool:
    """Only run this extractor on sites with restaurant-level evidence.

    MEASURED (38 manifests, 2026-06-11): every true restaurant has a MENU page
    type or >=2 distinct identity tokens (elkbabgi=4, zooba=4, buffalo=2+menu,
    mcdonalds=menu page); every false-fire site (gov education, hospital,
    jewelry/cosmetics e-commerce, university) has 0-1 and no MENU page.
    """
    if any(page.page_type == PageType.MENU for page in manifest.pages):
        return True
    text = " ".join(
        block.text or "" for page in manifest.pages for block in page.text_blocks
    )
    hits = sum(1 for rx in _STRONG_IDENTITY_TOKENS.values() if rx.search(text))
    return hits >= 2

# Ordered from more identity-level to more service-mode. Each match becomes one
# high-level offering using the source quote as evidence.
_OFFERING_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(authentic\s+egyptian\s+cuisine|egyptian\s+cuisine|traditional\s+egyptian\s+(?:food|cuisine|dishes))\b", re.I), "Authentic Egyptian Cuisine"),
    (re.compile(r"\b(eastern\s+(?:food|cuisine|dishes)|traditional\s+eastern\s+dishes)\b", re.I), "Traditional Eastern Dishes"),
    (re.compile(r"\b(grilled\s+(?:meats|dishes|food)|mixed\s+grill|grill\s+platters?)\b", re.I), "Grilled Dishes"),
    (re.compile(r"\b(stews?|molokhia|tagines?)\b", re.I), "Traditional Stews"),
    (re.compile(r"\b(family\s+dining|casual\s+dining|fine\s+dining|dine[-\s]?in)\b", re.I), "Dining Experience"),
    (re.compile(r"\b(takeaway|take[-\s]?out|delivery|order\s+online)\b", re.I), "Takeaway and Delivery"),
    (re.compile(r"\b(catering|event\s+catering|catering\s+services)\b", re.I), "Catering Services"),
]


def _quote(text: str, start: int = 0, end: int | None = None) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
    if end is None:
        end = min(len(text), 180)
    left = max(0, start - 60)
    right = min(len(text), end + 90)
    return text[left:right][:200]


def _candidate_blocks(manifest: ScrapeManifest) -> list[TextBlock]:
    out: list[TextBlock] = []
    for page in manifest.pages:
        if page.page_type not in _RESTAURANT_PAGE_TYPES:
            continue
        for block in page.text_blocks:
            text = block.text or ""
            if len(text.strip()) < 4:
                continue
            if _RESTAURANT_SIGNALS.search(text):
                out.append(block)
    return out


def extract_restaurant_offerings(manifest: ScrapeManifest, max_items: int = 6) -> list[Offering]:
    """Extract broad restaurant offerings with direct evidence only."""
    if not _passes_restaurant_gate(manifest):
        return []

    offerings: list[Offering] = []
    seen: set[str] = set()

    for block in _candidate_blocks(manifest):
        text = block.text or ""
        for pattern, name in _OFFERING_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            offerings.append(Offering(
                name=name,
                short_description=None,
                price_text=None,
                page_url=block.page_url,
                evidence=[EvidenceItem(
                    block_id=block.block_id,
                    page_url=block.page_url,
                    quote=_quote(text, m.start(), m.end()),
                    extractor="rule:restaurant_offering_text",
                )],
                confidence=Confidence.MEDIUM,
            ))
            if len(offerings) >= max_items:
                return offerings

    # The old last-resort fallback that emitted a fabricated "Restaurant Menu"
    # offering was REMOVED (2026-06-11): the name appeared nowhere in evidence
    # (zero-hallucination violation) and it false-fired on 7/8 measured sites
    # via the Arabic nav word "القائمة" ("menu"). A gated real restaurant with
    # no pattern match now honestly returns [] and the LLM extractor covers it.
    return offerings
