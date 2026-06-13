"""SERP-based competitor discovery for ECOMMERCE / online businesses.

Implements the router's `WebDiscoveryEngine` Protocol. For businesses the Places
(LOCAL) path can't reach, it finds market peers via a pluggable web-search
provider (search_providers.py) and returns them as `CompetitorProfile` objects —
evidence-grounded exactly like the Places path:

  * Every peer carries the QUERY + organic RANK that surfaced it (SelectionRecord.
    why_selected), so "why this peer" is always answerable.
  * Only real, scrapable domains survive: social profiles (Facebook/Instagram/...)
    and aggregators/marketplaces/review-sites (Amazon, Yelp, Wikipedia, G2, ...)
    are dropped — they are not direct competitors.
  * The subject's own domain is excluded.

It NEVER fabricates a peer. No provider, an empty result, or an all-filtered
result yields [] and the SWOT layer degrades to a grounded standalone analysis.
"""
from __future__ import annotations

from typing import List, Optional
from urllib.parse import urlparse

from .discovery import _get, _is_scrapable_site, _offering_name
from .models import (
    Candidate,
    CompetitorProfile,
    PeerFitBreakdown,
    SelectionRecord,
)
from .peer_match import TARGET_PEERS, expand_bilingual, tokenize
from .search_providers import SearchHit, SearchProvider, get_default_search_provider


def _field_text(profile, key: str) -> str:
    """Robust scalar read: handles object profiles (EvidencedField.value, enums)
    AND serialized dict profiles ({"value": ...}). Returns "" when absent."""
    val = _get(profile, key)
    if val is None:
        return ""
    if isinstance(val, dict):               # dict-wrapped EvidencedField
        val = val.get("value")
    val = getattr(val, "value", val)        # enum -> its .value
    return str(val).strip() if val else ""

# Directories / marketplaces / review aggregators / "X competitors" listicle &
# company-data sites / forums — never direct competitors. (Expanded after a live
# measurement: brand queries surfaced craft.co, gripsintelligence, weddingbee.)
_AGGREGATOR_HOSTS = {
    # marketplaces / encyclopedias / directories
    "wikipedia.org", "yelp.com", "tripadvisor.com", "yellowpages.com",
    "amazon.com", "ebay.com", "etsy.com", "alibaba.com", "aliexpress.com",
    "noon.com", "jumia.com", "walmart.com", "target.com",
    # social / generic platforms
    "crunchbase.com", "glassdoor.com", "indeed.com", "linkedin.com",
    "pinterest.com", "reddit.com", "quora.com", "medium.com", "youtube.com",
    "google.com", "bing.com", "apple.com", "play.google.com", "facebook.com",
    "instagram.com", "tiktok.com", "x.com", "twitter.com",
    # review / company-data / competitor-listicle / analytics sites
    "clutch.co", "g2.com", "capterra.com", "trustpilot.com", "producthunt.com",
    "craft.co", "owler.com", "gripsintelligence.com", "similarweb.com",
    "semrush.com", "ahrefs.com", "statista.com", "zoominfo.com", "6sense.com",
    "growjo.com", "datanyze.com", "enlyft.com", "slintel.com", "rocketreach.co",
    "comparably.com", "wappalyzer.com", "builtwith.com",
    # forums / Q&A / blog farms
    "weddingbee.com", "trustpilot.co.uk", "sitejabber.com", "knoji.com",
}


def _registrable(host: Optional[str]) -> Optional[str]:
    """Last two labels of a host (best-effort eTLD+1 without a PSL dependency)."""
    if not host:
        return None
    host = host.split(":")[0].removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else host or None


def _is_aggregator(host: Optional[str]) -> bool:
    reg = _registrable(host)
    return bool(reg) and reg in _AGGREGATOR_HOSTS


def _subject_registrable(profile) -> Optional[str]:
    for key in ("final_url", "source_url", "website", "url"):
        val = _get(profile, key)
        if val:
            return _registrable(urlparse(str(val)).netloc or str(val))
    return None


def _clean_title(title: str, host: Optional[str]) -> str:
    """A short brand-ish name: text before the first separator, else the host."""
    if title:
        for sep in (" | ", " - ", " – ", " — ", ": "):
            if sep in title:
                title = title.split(sep)[0]
                break
        title = title.strip()
    return title or (_registrable(host) or "competitor")


class SerpWebDiscoveryEngine:
    """Find online competitors via web search. Satisfies WebDiscoveryEngine."""
    name = "serp-web"

    def __init__(
        self,
        provider: Optional[SearchProvider] = None,
        *,
        max_peers: int = TARGET_PEERS,
        results_per_query: int = 10,
    ):
        # Honor an explicit provider=None as "no provider -> discover() returns []"
        # (the documented contract + the guard in discover()). The production factory
        # default_web_engine() resolves the default provider externally, so the
        # constructor must NOT silently go live on None (that made the no-provider
        # path hit the real network whenever a SERP key was in the environment).
        self.provider = provider
        self.max_peers = max_peers
        self.results_per_query = results_per_query

    # -- query construction (universal: brand-similarity + category) -----------
    def _queries(self, profile) -> tuple[List[str], Optional[str]]:
        # Robust to object AND dict profiles; never trusts category enum repr.
        brand = _field_text(profile, "name")
        category = _field_text(profile, "category")
        offerings = _get(profile, "offerings", default=[]) or []
        kw_source = " ".join(
            [n for n in (_offering_name(o) for o in offerings) if n]
            + ([category] if category else [])
        )
        # English head terms drive web search; bilingual variants stay available.
        kws = [k for k in expand_bilingual(list(dict.fromkeys(tokenize(kw_source))))
               if k and k.isascii()][:3]
        languages = [str(l).lower()[:2] for l in (_get(profile, "languages", default=[]) or [])]
        hl = languages[0] if languages else None

        # Category/offering query FIRST — it returns real businesses in the space.
        # Brand "competitors/alternatives" queries are secondary: they tend to
        # surface listicle/data-aggregator pages (filtered below), but also
        # occasionally a genuine rival, so we keep them as a supplement.
        # Rely on the offering KEYWORDS for the vertical (the literal category word
        # like "ecommerce"/"services_b2b" is noise; "restaurant" etc. is useful).
        queries: List[str] = []
        if kws:
            queries.append("best " + " ".join(kws))
        elif category:
            queries.append(f"top {category}")
        if brand:
            queries.append(f"{brand} competitors")
            queries.append(f"{brand} alternatives")
        # de-dup while preserving order
        seen_q, ordered = set(), []
        for q in queries:
            if q and q not in seen_q:
                seen_q.add(q)
                ordered.append(q)
        return ordered, hl

    # -- WebDiscoveryEngine.discover ------------------------------------------
    def discover(self, profile, manifest=None) -> List[CompetitorProfile]:
        if self.provider is None:
            return []
        queries, hl = self._queries(profile)
        if not queries:
            return []

        subject = _subject_registrable(profile)
        seen: set[str] = set()
        peers: List[CompetitorProfile] = []

        for query in queries:
            hits = self.provider.search(query, num=self.results_per_query, hl=hl)
            for hit in hits:
                peer = self._to_peer(hit, query, subject, seen)
                if peer is not None:
                    peers.append(peer)
                    if len(peers) >= self.max_peers:
                        return peers
        return peers

    def _to_peer(
        self, hit: SearchHit, query: str, subject: Optional[str], seen: set,
    ) -> Optional[CompetitorProfile]:
        host = urlparse(hit.link).netloc
        reg = _registrable(host)
        if not reg or reg in seen:
            return None
        if subject and reg == subject:
            return None
        if not _is_scrapable_site(hit.link) or _is_aggregator(host):
            return None
        seen.add(reg)

        # Benchmark the competitor's HOMEPAGE, not the deep page that ranked
        # (e.g. a "/blogs/...-vs-us" comparison post). The matrix scrapes this URL.
        parsed = urlparse(hit.link)
        home = f"{parsed.scheme or 'https'}://{parsed.netloc}/"

        name = _clean_title(hit.title, host)
        why = f"web search peer (rank {hit.rank}) for query: {query!r}"
        candidate = Candidate(
            place_id="",                # no Places id for a web-sourced peer
            name=name,
            website=home,
            formatted_address=None,
        )
        selection = SelectionRecord(
            place_id="",
            name=name,
            website=home,
            peer_fit_score=round(1.0 / hit.rank, 3) if hit.rank else 0.0,
            breakdown=PeerFitBreakdown(total=round(1.0 / hit.rank, 3) if hit.rank else 0.0),
            why_selected=why,
        )
        return CompetitorProfile(
            candidate=candidate,
            selection=selection,
            reviews=[],
            has_scrapable_site=True,    # filtered to real scrapable domains above
            is_local=False,             # web-sourced benchmark, not a local peer
        )


def default_web_engine() -> "SerpWebDiscoveryEngine | None":
    """Production factory: a live SERP engine when a search key is configured,
    else None (caller falls back to the router's NullWebDiscoveryEngine)."""
    provider = get_default_search_provider()
    return SerpWebDiscoveryEngine(provider) if provider is not None else None
