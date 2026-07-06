"""Trend engine: ride a CURRENT trend relevant to the business.

    from trends import top_trends, keywords_from_profile
    trends = top_trends(keywords_from_profile(profile), require_match=True)
"""
from .sources import (
    TrendItem, TrendSource, default_trend_sources,
    HackerNewsSource, RedditSource, DevToSource,
)
from .engine import (
    fetch_trends, rank_trends, match_to_keywords, top_trends, top_trends_bounded,
    keywords_from_profile,
)

__all__ = [
    "TrendItem", "TrendSource", "default_trend_sources",
    "HackerNewsSource", "RedditSource", "DevToSource",
    "fetch_trends", "rank_trends", "match_to_keywords", "top_trends", "top_trends_bounded",
    "keywords_from_profile",
]
