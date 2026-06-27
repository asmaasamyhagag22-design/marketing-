"""Trend sources — pull currently-trending items from FREE, keyless public APIs.

Each source satisfies the `TrendSource` protocol and returns a list of `TrendItem`.
stdlib-only (urllib), and NEVER raises — a network/parse error yields `[]` so one bad
source can't break a campaign run (same discipline as `competitor/search_providers.py`).

No API key needed: HackerNews (Firebase), Reddit (public JSON, needs a UA), Dev.to API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from scraper.net import get_json as _resilient_get_json

_UA = "Mozilla/5.0 (compatible; MarketingTrends/0.1)"


@dataclass
class TrendItem:
    """One trending item. `score` is the source's raw popularity (HN points / Reddit
    upvotes / Dev.to reactions); `trend_score` (0..1) and `matched_terms` are filled by
    the engine."""
    title: str
    url: str
    source: str
    score: float = 0.0
    created_ts: Optional[float] = None        # unix seconds (UTC)
    trend_score: float = 0.0
    matched_terms: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class TrendSource(Protocol):
    name: str

    def fetch(self, limit: int = 30) -> list[TrendItem]:
        ...


def _get_json(url: str, *, timeout: int = 8):
    """GET + parse JSON; returns the decoded object or None on ANY failure.

    Delegates to the shared resilient fetcher (bounded retry + per-host CIRCUIT
    BREAKER) so a dead/slow source (e.g. HackerNews, which fans out one call per
    story) is retried on a transient blip but stops being hammered once it has failed
    repeatedly — instead of paying the full timeout on every one of dozens of calls."""
    return _resilient_get_json(url, timeout=timeout, headers={"User-Agent": _UA})


def _parse_iso(ts) -> Optional[float]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


class HackerNewsSource:
    """HackerNews top stories via the public Firebase API (no key)."""
    name = "hackernews"
    BASE = "https://hacker-news.firebaseio.com/v0"

    def fetch(self, limit: int = 30) -> list[TrendItem]:
        ids = _get_json(f"{self.BASE}/topstories.json") or []
        out: list[TrendItem] = []
        for i in ids[: max(0, limit)]:
            item = _get_json(f"{self.BASE}/item/{i}.json")
            if not item or item.get("type") != "story" or item.get("dead") or item.get("deleted"):
                continue
            title = item.get("title") or ""
            if not title:
                continue
            out.append(TrendItem(
                title=title,
                url=item.get("url") or f"https://news.ycombinator.com/item?id={i}",
                source=self.name,
                score=float(item.get("score") or 0),
                created_ts=item.get("time"),
            ))
        return out


class RedditSource:
    """Hot posts from a few subreddits via Reddit's public JSON (no key; needs a UA)."""
    name = "reddit"

    def __init__(self, subreddits: Optional[list[str]] = None):
        self.subreddits = subreddits or ["technology", "business", "marketing", "smallbusiness"]

    def fetch(self, limit: int = 30) -> list[TrendItem]:
        per = max(1, limit // max(1, len(self.subreddits)))
        out: list[TrendItem] = []
        for sub in self.subreddits:
            data = _get_json(f"https://www.reddit.com/r/{sub}/hot.json?limit={per}")
            for child in ((data or {}).get("data") or {}).get("children", []):
                d = child.get("data") or {}
                if d.get("stickied") or not d.get("title"):
                    continue
                permalink = d.get("permalink") or ""
                out.append(TrendItem(
                    title=d.get("title") or "",
                    url=("https://www.reddit.com" + permalink) if permalink else (d.get("url") or ""),
                    source=self.name,
                    score=float(d.get("ups") or d.get("score") or 0),
                    created_ts=d.get("created_utc"),
                ))
        return out


class DevToSource:
    """Top recent articles from the Dev.to public API (no key)."""
    name = "devto"

    def fetch(self, limit: int = 30) -> list[TrendItem]:
        data = _get_json(f"https://dev.to/api/articles?top=7&per_page={min(max(1, limit), 100)}")
        out: list[TrendItem] = []
        for a in (data or []):
            if not isinstance(a, dict) or not a.get("title"):
                continue
            out.append(TrendItem(
                title=a.get("title") or "",
                url=a.get("url") or "",
                source=self.name,
                score=float(a.get("public_reactions_count") or 0),
                created_ts=_parse_iso(a.get("published_timestamp")),
            ))
        return out


def default_trend_sources() -> list[TrendSource]:
    """The keyless sources used by default."""
    return [HackerNewsSource(), RedditSource(), DevToSource()]
