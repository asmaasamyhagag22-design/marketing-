"""Trend engine — fetch, RANK, and MATCH trending items to a business so a campaign can
ride a CURRENT trend (relevant + fresh), not a generic evergreen angle.

Ranking (v1, no time-series): per-source popularity is normalized (so HN points and
Dev.to reactions are comparable) and combined with a recency decay:

    trend_score = 0.7 * normalized_popularity + 0.3 * recency      (recency = 1 at now, 0.5 at 24h)

Matching: a trend is RELEVANT when its title shares a keyword with the business
(category / offerings / value props). `top_trends` returns matched trends first, each
ranked by trend_score — the campaign picks the strongest on-topic moment.

Pure: sources are injected (defaults are keyless), nothing here mutates global state.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Optional

from .sources import TrendItem, TrendSource, default_trend_sources

logger = logging.getLogger(__name__)

# Generic words that must never count as a topical match (they match everything). The
# default trend sources (HN / Reddit / Dev.to) are TECH-skewed, so a plain word shared with
# a tech headline is almost always a coincidence — hence the extra cross-domain + tech-
# ambiguous terms below. (Pure-numeric tokens like years are dropped separately.)
_STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "our", "are", "from", "this", "that",
    "new", "best", "top", "how", "why", "what", "online", "service", "services",
    "business", "company", "egypt", "near", "home", "more", "get", "all",
    # generic
    "free", "day", "days", "time", "way", "ways", "make", "made", "use", "using", "world",
    "life", "people", "year", "years", "week", "month", "thing", "things", "good", "great",
    "here", "into", "out", "about", "over", "just", "like", "one", "two", "now", "today",
    # tech-ambiguous (match tech news for ANY business)
    "app", "apps", "tech", "data", "web", "api", "code", "dev", "software", "startup",
    "startups", "digital", "tool", "tools", "update", "updates", "release", "launch",
    "review", "reviews", "guide", "tips", "news", "app",
}


def fetch_trends(sources: Optional[list[TrendSource]] = None, *, limit_per_source: int = 30) -> list[TrendItem]:
    """Aggregate items from all sources. A source that fails (down / schema-drifted) is
    logged as a WARNING and contributes nothing — so a silently-empty trend list is
    traceable to which source(s) failed, not mistaken for 'no trends'."""
    sources = sources if sources is not None else default_trend_sources()
    items: list[TrendItem] = []
    failed = 0
    for s in sources:
        try:
            got = s.fetch(limit_per_source) or []
            items.extend(got)
            if not got:
                logger.warning("trend source %r returned no items", getattr(s, "name", s))
        except Exception as exc:  # noqa: BLE001 — one bad source must not break the rest
            failed += 1
            logger.warning("trend source %r failed: %s", getattr(s, "name", s), exc)
    if failed and not items:
        logger.warning("ALL %d trend source(s) failed — trend list is empty", failed)
    return items


def rank_trends(items: list[TrendItem], *, now: Optional[float] = None) -> list[TrendItem]:
    """Set each item's `trend_score` (popularity normalized per source + recency) and
    return the list sorted by it, highest first. Mutates the items in place."""
    now = now if now is not None else time.time()
    by_source: dict[str, list[TrendItem]] = defaultdict(list)
    for it in items:
        by_source[it.source].append(it)
    for group in by_source.values():
        mx = max((it.score for it in group), default=0.0) or 1.0
        for it in group:
            pop = max(0.0, it.score) / mx
            age_h = max(0.0, (now - it.created_ts) / 3600.0) if it.created_ts else 48.0
            recency = 1.0 / (1.0 + age_h / 24.0)
            it.trend_score = round(0.7 * pop + 0.3 * recency, 4)
    return sorted(items, key=lambda it: it.trend_score, reverse=True)


def match_to_keywords(items: list[TrendItem], keywords: list[str]) -> list[TrendItem]:
    """Tag each item with the business keywords that appear (whole-word) in its title.
    Mutates `matched_terms` in place and returns the list."""
    import re
    kws = sorted({k.lower().strip() for k in keywords
                  if k and len(k.strip()) >= 3
                  and not k.strip().isdigit()          # a bare year/number is not a topic
                  and k.lower().strip() not in _STOPWORDS},
                 key=len, reverse=True)
    for it in items:
        title = it.title.lower()
        it.matched_terms = tuple(k for k in kws if re.search(r"\b" + re.escape(k) + r"\b", title))
    return items


def keywords_from_profile(profile: dict[str, Any]) -> list[str]:
    """Pull topical keywords from a BusinessProfile dict (category + offering names +
    value-prop / tagline words). Best-effort; tolerant of dict-wrapped EvidencedFields."""
    def _val(x):
        return x.get("value") if isinstance(x, dict) and "value" in x else x

    out: list[str] = []
    cat = _val(profile.get("category"))
    if isinstance(cat, str):
        out += cat.replace("_", " ").split()
    for o in (profile.get("offerings") or []):
        name = _val(o.get("name") if isinstance(o, dict) else o)
        if isinstance(name, str):
            out += name.split()
    for vp in (profile.get("value_propositions") or [])[:5]:
        # A value_proposition is an EvidencedField -> its text is under 'value' (NOT
        # 'text'); _val unwraps {'value': ...} and passes a plain string through.
        v = _val(vp)
        if isinstance(v, str):
            out += v.split()
    tagline = _val(profile.get("tagline"))
    if isinstance(tagline, str):
        out += tagline.split()
    # Normalize: strip punctuation, drop short/stopwords, dedupe (order-preserving).
    seen: set[str] = set()
    cleaned: list[str] = []
    for w in out:
        w = "".join(ch for ch in w if ch.isalnum() or ch in "-&").strip("-&").lower()
        if len(w) >= 3 and not w.isdigit() and w not in _STOPWORDS and w not in seen:
            seen.add(w)                                 # drop bare years/numbers too
            cleaned.append(w)
    return cleaned


def top_trends(
    keywords: list[str],
    *,
    sources: Optional[list[TrendSource]] = None,
    limit_per_source: int = 30,
    top_k: int = 10,
    require_match: bool = False,
    now: Optional[float] = None,
) -> list[TrendItem]:
    """Fetch → rank → match, then return the strongest trends with on-topic ones FIRST.
    `require_match=True` drops trends that share no keyword with the business."""
    if sources is None:                                    # pick sources by the brand's vertical
        sources = default_trend_sources(keywords=keywords)
    items = rank_trends(fetch_trends(sources, limit_per_source=limit_per_source), now=now)
    match_to_keywords(items, keywords)
    if require_match:
        items = [it for it in items if it.matched_terms]
    items.sort(key=lambda it: (len(it.matched_terms), it.trend_score), reverse=True)
    return items[: max(0, top_k)]
