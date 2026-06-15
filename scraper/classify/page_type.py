"""Page-type classification.

Given a URL (and optionally its anchor text from the linking page),
return a (page_type, tier) pair.

Matches against URL path AND anchor text using bilingual patterns
from config.PAGE_TYPE_PATTERNS. First match wins (patterns are
ordered by tier).

Important v0.1 crawl-policy rule:
- blog/news index pages may be fetched as LOW priority.
- blog/news/article detail pages are SKIP so they do not consume the
  limited crawl budget needed for business-profile pages such as
  contact, about, services, products, pricing, booking, menu, and FAQ.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from ..config import PAGE_TYPE_PATTERNS
from ..schemas import PageTier, PageType


_FLAT_PATTERNS = []
for pt, tier, patterns in PAGE_TYPE_PATTERNS:
    for p in patterns:
        _FLAT_PATTERNS.append((p.lower(), pt, tier))


_CONTENT_INDEX_MARKERS = {
    # English
    "blog", "news", "article", "articles", "post", "posts", "press",
    "event", "events", "story", "stories",

    # Arabic / transliteration
    "akhbar", "madona", "maqalat", "اخبار", "أخبار", "مدونة", "مقالات",
}

_DETAIL_MARKERS = {
    "detail", "details", "news-detail", "news-details", "news_detail",
    "news_details", "single", "read", "view", "item",
    "تفاصيل", "التفاصيل",
}

_DETAIL_QUERY_KEYS = {
    "id", "post", "post_id", "article", "article_id", "news", "news_id",
    "event", "event_id", "story", "story_id", "p",
}

# Legal / policy tokens. These must win OVER the generic pattern scan, because a
# URL like /policies/terms-of-service contains "service" and would otherwise match
# SERVICES (HIGH) and steal a real-content crawl slot. MEASURED: 9/63 legal URLs
# across 7 saved sites were mis-tiered as HIGH/MEDIUM content. Tokens are matched
# whole (split on '-'), so "policymaker" / "services" do NOT match.
_LEGAL_TOKENS = {
    "terms", "tos", "privacy", "policy", "policies", "legal", "disclaimer",
    "cookie", "cookies", "gdpr", "refund", "refunds", "eula", "copyright",
}


def _is_legal_page(url: str, anchor_text: str = "") -> bool:
    """True for terms / privacy / policy / legal URLs — matched on whole tokens of
    the path segments (and the anchor), so SERVICES etc. are not stolen by 'service'
    inside 'terms-of-service'."""
    _path, segments, _q = _normalized_path(url)
    tokens: set[str] = set()
    for seg in segments:
        tokens.update(seg.split("-"))
    tokens.update((anchor_text or "").lower().replace("_", "-").replace("&", " ").split())
    return bool(tokens & _LEGAL_TOKENS)


def _normalized_path(url: str) -> tuple[str, list[str], dict[str, list[str]]]:
    """Return normalized path, path segments, query params for a URL."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "", [], {}

    path = (parsed.path or "").lower()
    normalized = path.replace("_", "-")
    segments = [seg for seg in normalized.strip("/").split("/") if seg]
    query = parse_qs(parsed.query or "")
    return normalized, segments, query


def _contains_any(text: str, markers: set[str]) -> bool:
    lower = (text or "").lower().replace("_", "-")
    return any(m.lower().replace("_", "-") in lower for m in markers)


def _is_blog_or_news_detail(url: str, anchor_text: str = "") -> bool:
    """Detect content-detail URLs that should not consume crawl budget.

    Examples to skip:
    - /news_details.php?id=1072
    - /news-detail/1072
    - /blog/how-to-choose-a-service
    - /articles/my-article-title

    Examples to keep as LOW:
    - /news.php
    - /blog
    - /articles
    """
    path, segments, query = _normalized_path(url)
    anchor = (anchor_text or "").lower().replace("_", "-")
    haystack = f"{path} {anchor}"

    has_content_marker = _contains_any(haystack, _CONTENT_INDEX_MARKERS)
    if not has_content_marker:
        return False

    # Explicit detail naming, e.g. news_details.php?id=1072.
    if _contains_any(haystack, _DETAIL_MARKERS):
        return True

    # Query id on a content page usually means detail page.
    query_keys = {k.lower() for k in query.keys()}
    if query_keys & _DETAIL_QUERY_KEYS:
        return True

    # /blog/<slug>, /news/<slug>, /articles/<slug> => detail-like.
    # Keep only top-level index such as /blog or /news.
    if len(segments) >= 2:
        first = segments[0]
        if _contains_any(first, _CONTENT_INDEX_MARKERS):
            return True

    return False


def classify_url(url: str, anchor_text: str = "") -> tuple[PageType, PageTier]:
    """Return (page_type, tier) for this URL.

    Matching strategy (improved 2026-05):
      1. Blog/news detail pages skip before any other matching.
      2. Path is split into segments. We try the LAST segment first
         (most specific), then earlier segments, then the whole path.
         This fixes cases like /branches/all/menu which used to match
         "branches" on the whole path and never reach "menu".
      3. Within each candidate haystack, the first matching pattern in
         _FLAT_PATTERNS wins (preserves the existing ordering for
         disambiguation, e.g. CATERING before SERVICES).
      4. Anchor text is matched against the whole pattern list as a
         final fallback — anchors rarely contain hierarchy.

    Backward-compatible for single-segment paths: a URL like /menu has
    one segment which is also the whole path, so the result is unchanged.
    """
    if _is_blog_or_news_detail(url, anchor_text):
        return PageType.BLOG, PageTier.SKIP

    # Legal/policy pages have ~zero marketing value and must not consume the crawl
    # budget — and crucially must win over the generic scan (terms-of-service -> SKIP,
    # not SERVICES). Checked BEFORE the pattern scan.
    if _is_legal_page(url, anchor_text):
        return PageType.LEGAL, PageTier.SKIP

    try:
        path = urlparse(url).path.lower()
    except Exception:
        path = ""

    haystack_anchor = (anchor_text or "").lower().replace("_", "-")
    whole_path = path.replace("_", "-")

    # Split into non-empty segments. e.g. "/branches/all/menu" → ["branches","all","menu"]
    segments = [s for s in whole_path.split("/") if s]

    # Build the ordered list of haystacks to try.
    # 1. Last segment, then earlier segments (right-to-left = most specific first).
    # 2. Whole path (for single-segment paths and multi-segment patterns like "store-locator").
    haystacks: list[str] = []
    for seg in reversed(segments):
        haystacks.append(seg)
    if whole_path and whole_path not in haystacks:
        haystacks.append(whole_path)

    for haystack in haystacks:
        for pattern, page_type_str, tier_str in _FLAT_PATTERNS:
            pat = pattern.replace("_", "-").lower()
            if pat in haystack:
                try:
                    return PageType(page_type_str), PageTier(tier_str)
                except ValueError:
                    return PageType.OTHER, PageTier.LOW

    # Anchor-text fallback — used when the URL itself was uninformative.
    if haystack_anchor:
        for pattern, page_type_str, tier_str in _FLAT_PATTERNS:
            pat = pattern.replace("_", "-").lower()
            if pat in haystack_anchor:
                try:
                    return PageType(page_type_str), PageTier(tier_str)
                except ValueError:
                    return PageType.OTHER, PageTier.LOW

    return PageType.OTHER, PageTier.LOW


def classify_homepage(_url: str) -> tuple[PageType, PageTier]:
    """Homepage is the entry URL — fixed type/tier regardless of slug."""
    return PageType.HOMEPAGE, PageTier.HIGH