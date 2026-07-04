"""Competitor discovery orchestrator.

Flow:
    BusinessProfile
        -> build_match_criteria()        # the ONLY adapter to your schema
        -> [geocode if needed]
        -> Places search (nearby, or text for online-only)
        -> compute distances (haversine)
        -> select_peers()                 # hard filters + peer-fit + dedup
        -> fetch reviews for the chosen peers
        -> PeerMatchResult

What this module does NOT do: it does not scrape the competitors' websites and
it does not build the Comparative Gap Matrix or the SWOT. Those are the next
chunk and they consume `PeerMatchResult`.
"""

from __future__ import annotations

import math
from typing import List, Optional

from .models import CompetitorProfile, MatchCriteria, PeerMatchResult
from .peer_match import (
    TARGET_PEERS, select_peers, tokenize, passes_hard_filters, expand_bilingual,
)
from .places_client import PlacesClient


# ---------------------------------------------------------------------------
# Category -> Google Places type strings.
# STARTER MAP for your four verticals. Refine the right-hand side against the
# current Places "Place Types (New)" table — Google updates it (last update
# Feb 2026). These are the search/filter types, not your internal labels.
# ---------------------------------------------------------------------------
CATEGORY_TYPE_MAP = {
    # These are GENEROUS families used only by the hard "is it the right kind of
    # place at all" sanity filter (candidate.types must intersect this set). They
    # are intentionally wide so legit sub-vertical variants are not excluded by
    # Places' inconsistent typing. Fine relevance (e.g. derma vs radiology) comes
    # from the offerings-driven text query + the sub_vertical score, NOT from here.
    # Extra type strings that don't exist in Places are harmless in a filter set.
    "restaurant": ["restaurant", "cafe", "bakery", "bar", "meal_takeaway",
                   "meal_delivery", "food", "fast_food_restaurant"],
    "clinic": ["doctor", "dentist", "dental_clinic", "medical_clinic", "medical_center",
               "hospital", "physiotherapist", "spa", "beauty_salon", "skin_care_clinic",
               "wellness_center", "chiropractor"],
    "skincare": ["beauty_salon", "skin_care_clinic", "spa", "cosmetics_store",
                 "hair_care", "wellness_center", "doctor", "medical_clinic"],
    "education": ["school", "primary_school", "secondary_school", "university",
                  "preschool", "tutoring_center", "library"],
}


# ===========================================================================
# ADAPTER  ->  the only place that reads your BusinessProfile.
# Adjust the attribute names on the right to match your real BusinessProfile.
# Everything below the adapter is schema-agnostic.
# ===========================================================================
def build_match_criteria(profile, *,
                         category_type_map: Optional[dict] = None) -> MatchCriteria:
    category_type_map = category_type_map or CATEGORY_TYPE_MAP

    # --- category (your internal label) ---
    category = _get(profile, "category", default="") or ""
    # category may be a BusinessCategory enum (a str-subclass): use its .value.
    # str(SomeEnum.X) yields "BusinessCategory.X" — that broke the type-map lookup
    # AND leaked "BusinessCategory.ECOMMERCE" into the Places text query.
    category_str = str(getattr(category, "value", category)).strip()
    place_types = category_type_map.get(category_str.lower(), [])

    # --- offerings + category -> keyword set for name overlap ---
    # Use each offering's NAME only. str(o) would dump the whole object repr
    # (field names + evidence + page_url) into the query, producing garbage like
    # "name short description evidence block id https ... llm" -> 0 Places hits.
    offerings = _get(profile, "offerings", default=[]) or []
    offering_text = " ".join(n for n in (_offering_name(o) for o in offerings) if n)
    offering_text = (offering_text + " " + category_str).strip()
    offering_keywords = expand_bilingual(list(dict.fromkeys(tokenize(offering_text))))

    # --- audience tier + confidence ---
    audience_tier = _normalize_tier(_get(profile, "audience_type", default=None))
    audience_conf = float(_get(profile, "audience_confidence", default=0.0) or 0.0)

    # --- languages ---
    languages = _get(profile, "languages", default=[]) or []
    languages = [str(l).lower()[:2] for l in languages]

    # --- location: prefer explicit lat/lng, else None (orchestrator geocodes) ---
    lat = _get(profile, "lat", default=None)
    lng = _get(profile, "lng", default=None)
    address = _get(profile, "physical_address", default=None)

    # --- online-only heuristic: no address and no coords. Override if you have
    #     a real flag on the profile. ---
    is_online_only = not address and lat is None and lng is None

    # --- subject's own Places review count (often None pre-enrichment) ---
    review_count_self = _get(profile, "review_count", default=None)

    crit = MatchCriteria(
        category=category_str,
        place_types=place_types,
        offering_keywords=offering_keywords,
        audience_tier=audience_tier,
        audience_confidence=audience_conf,
        languages=languages,
        lat=lat,
        lng=lng,
        address=address,
        is_online_only=is_online_only,
        review_count_self=review_count_self,
    )
    return crit


def _get(obj, name, default=None):
    """Read attr or dict key; unwrap a `.value` wrapper if present (your
    BusinessProfile uses name.value etc.).

    Handles BOTH profile shapes: the OBJECT profile (EvidencedField with a .value
    attribute — the CLI path) and the SERIALIZED dict profile (the web-API path,
    where an EvidencedField arrives as {"value": ..., "evidence": [...]}). The
    dict shape was NOT unwrapped before, so on the web path the whole evidence
    dict leaked into the Places text query as its repr — a garbage query that
    made discovery return 0 usable peers (measured root cause of the always-
    standalone, no-Threats/no-Opportunities SWOT in the web app)."""
    val = getattr(obj, name, None)
    if val is None and isinstance(obj, dict):
        val = obj.get(name)
    if val is None:
        return default
    if isinstance(val, dict) and "value" in val:
        inner = val.get("value")
        return inner if inner is not None else default
    inner = getattr(val, "value", None)
    return inner if inner is not None else val


def _offering_name(o) -> str:
    """The offering's display name only — never str(o) on a model (which serializes
    the whole Offering object, leaking field names + evidence + URLs into the query).
    Handles all three offering shapes: plain string, dict, or Offering object —
    and BOTH EvidencedField shapes (object .value / serialized {"value": ...})."""
    if isinstance(o, str):
        return o.strip()
    name = o.get("name") if isinstance(o, dict) else getattr(o, "name", None)
    if isinstance(name, dict) and "value" in name:      # serialized EvidencedField
        name = name.get("value")
    inner = getattr(name, "value", None)                # object EvidencedField
    name = inner if inner is not None else name
    return str(name).strip() if name else ""


def _normalize_tier(raw) -> Optional[str]:
    if not raw:
        return None
    s = str(raw).lower()
    if any(w in s for w in ("premium", "luxury", "high")):
        return "premium"
    if any(w in s for w in ("budget", "low", "cheap", "economy")):
        return "budget"
    if any(w in s for w in ("mid", "medium", "mass")):
        return "mid"
    return None


# ---------------------------------------------------------------------------
def haversine_m(lat1, lng1, lat2, lng2) -> Optional[float]:
    if None in (lat1, lng1, lat2, lng2):
        return None
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
def discover_competitors(
    profile,
    client: PlacesClient,
    *,
    radius_m: float = 15000,
    candidate_pool: int = 20,
    target: int = TARGET_PEERS,
    require_website: bool = False,
    min_scrapable_benchmarks: int = 2,
    fetch_reviews: bool = True,
    category_type_map: Optional[dict] = None,
) -> PeerMatchResult:
    crit = build_match_criteria(profile, category_type_map=category_type_map)
    address = crit.address
    notes: List[str] = []

    if not crit.place_types:
        notes.append(f"no Places type mapping for category '{crit.category}'")

    # ---- build the sub-vertical query ----
    # THIS is the lever that makes the pool relevant. Searching the broad category
    # ("clinic") ranked by popularity returns the biggest medical places nearby,
    # not the right *kind* of business. A query built from offerings ("laser skin
    # acne dermatology clinic") makes Google return actual peers. We deliberately
    # do NOT pass includedType: Places typing is inconsistent (a derma clinic may
    # be typed medical_clinic, skin_care_clinic, or beauty_salon), so a hard type
    # filter at retrieval would drop real peers. Type sanity is handled by the
    # (generous) hard-filter family + the sub_vertical score instead.
    q_terms = list(crit.offering_keywords[:6]) + ([crit.category] if crit.category else [])
    text_query = " ".join(t for t in q_terms if t).strip() or crit.category

    # ---- get candidates ----
    if crit.is_online_only:
        notes.append(f"online-only: text search {text_query!r}, proximity dropped")
        candidates = client.search_text(text_query, max_results=candidate_pool)
    else:
        if crit.lat is None or crit.lng is None:
            if not address:
                notes.append("no coordinates and no address; cannot run nearby search")
                return PeerMatchResult([], True, 0, 0, notes)
            # Prefer Places text search (needs only the Places API enabled).
            geo = client.geocode_via_places(address)
            if geo:
                notes.append(f"resolved center via Places text search -> ({geo[0]:.5f}, {geo[1]:.5f})")
            else:
                geo = client.geocode_address(address)  # fallback: Geocoding API
                if geo:
                    notes.append(f"resolved center via Geocoding API -> ({geo[0]:.5f}, {geo[1]:.5f})")
            if not geo:
                err = getattr(client, "last_geocode_error", None)
                notes.append(
                    f"could not resolve coordinates for {address!r}. "
                    f"Places text search returned nothing"
                    + (f"; Geocoding API said: {err}" if err else "")
                    + ". Fix: pass lat/lng directly in the profile, or enable the "
                    "Geocoding API on your key."
                )
                return PeerMatchResult([], True, 0, 0, notes)
            crit.lat, crit.lng = geo
        notes.append(f"text search {text_query!r} biased to "
                     f"({crit.lat:.4f},{crit.lng:.4f}) r={radius_m}m")
        candidates = client.search_text(text_query, lat=crit.lat, lng=crit.lng,
                                        radius_m=radius_m, max_results=candidate_pool)

    # drop the subject itself if it appears (match by website domain / exact name)
    candidates = [c for c in candidates if not _is_self(c, profile)]

    # ---- distances ----
    for c in candidates:
        c.distance_m = haversine_m(crit.lat, crit.lng, c.lat, c.lng)

    # locationBias is a bias, not a hard limit, so cap to the radius for a local set
    if not crit.is_online_only:
        before = len(candidates)
        candidates = [c for c in candidates
                      if c.distance_m is None or c.distance_m <= radius_m]
        dropped = before - len(candidates)
        if dropped:
            notes.append(f"dropped {dropped} candidate(s) beyond {radius_m}m")

    # ---- per-candidate hard-filter audit (explains a thin result) ----
    audit = []
    for c in candidates:
        ok, reason = passes_hard_filters(c, crit, require_website=require_website)
        audit.append({
            "name": c.name,
            "type": c.primary_type,
            "reviews": c.review_count,
            "website": c.website,
            "dist_km": round(c.distance_m / 1000, 1) if c.distance_m is not None else None,
            "passed": ok,
            "reason": reason,
        })

    # ---- select (two-tier) ----
    ranked, stats = select_peers(candidates, crit, require_website=require_website)

    # Local tier: top `target` by fit — the close, representative peers that drive
    # review themes (the local customer voice).
    local = ranked[:target]
    local_ids = {c.place_id for c, _ in local}
    n_scrapable_local = sum(1 for c, _ in local if _is_scrapable_site(c.website))

    # Benchmark tier: pull the best scrapable peers (above floor) NOT already local,
    # so the matrix has something to scrape for the dimension comparison. Capped so
    # we don't drag in many far/big clinics.
    benchmarks: List = []
    need = max(0, min_scrapable_benchmarks - n_scrapable_local)
    if need:
        for c, rec in ranked:
            if c.place_id in local_ids:
                continue
            if _is_scrapable_site(c.website):
                benchmarks.append((c, rec))
                if len(benchmarks) >= need:
                    break

    chosen = list(local) + benchmarks  # local first, then added benchmarks

    if len(local) < target:
        notes.append(
            f"thin local tier: only {len(local)} of {target} peers cleared the floor "
            f"({stats['passed_filters']} passed filters of {stats['considered']} considered). "
            f"Not padding with sub-floor candidates."
        )

    # ---- reviews + build profiles for both tiers ----
    competitors: List[CompetitorProfile] = []
    for cand, rec in chosen:
        reviews = client.get_reviews(cand.place_id) if fetch_reviews else []
        competitors.append(CompetitorProfile(
            candidate=cand, selection=rec, reviews=reviews,
            has_scrapable_site=_is_scrapable_site(cand.website),
            is_local=cand.place_id in local_ids,
        ))

    n_scrapable = sum(1 for c in competitors if c.has_scrapable_site)
    n_added = len(benchmarks)
    notes.append(
        f"tiers: {len(local)} local (review themes) + {n_added} added benchmark(s); "
        f"{n_scrapable} scrapable peer(s) for the dimension matrix"
    )
    if n_scrapable == 0:
        notes.append(
            "no scrapable competitor found even after the benchmark pass; the matrix "
            "will rely on Places signals only (rating / reviews / price level). Consider "
            "a larger radius if you need scraped-dimension comparison."
        )

    return PeerMatchResult(
        competitors=competitors,
        thin_peer_set=len(local) < target,
        candidates_considered=stats["considered"],
        candidates_passed_filters=stats["passed_filters"],
        notes=notes,
        audit=audit,
    )


_SOCIAL_HOSTS = {
    "facebook.com", "m.facebook.com", "fb.com", "fb.me", "instagram.com",
    "tiktok.com", "linktr.ee", "wa.me", "api.whatsapp.com", "twitter.com",
    "x.com", "youtube.com", "youtu.be", "t.me",
}


def _is_scrapable_site(url: Optional[str]) -> bool:
    """True if the URL is a real domain we could scrape (not a social profile)."""
    if not url:
        return False
    from .peer_match import _domain
    d = _domain(url)
    return bool(d) and d not in _SOCIAL_HOSTS


def _is_self(cand, profile) -> bool:
    """Best-effort: drop the subject business if Places returned it."""
    own_site = _get(profile, "website", default=None) or _get(profile, "url", default=None)
    if own_site and cand.website:
        from .peer_match import _domain
        if _domain(own_site) and _domain(own_site) == _domain(cand.website):
            return True
    own_name = _get(profile, "name", default=None)
    if own_name and cand.name:
        from .peer_match import normalize_text
        if normalize_text(str(own_name)) == normalize_text(cand.name):
            return True
    return False


def find_subject_places(profile, client, *, max_results: int = 8):
    """Find the SUBJECT's own Places listing (rating / review volume / price tier).

    Without it the matrix's Places dimensions have no subject value, every Places gap
    is "n/a", and the SWOT can never emit a market-position THREAT ("your review volume
    is below the peer average") — the measured root cause of the always-empty Threats
    quadrant on the web path.

    Grounded matching only: the candidate must match the subject by WEBSITE registrable
    domain (strongest signal — it's the subject's own site) or by exact normalized name.
    No fuzzy guessing: grounding the SWOT in someone ELSE's ratings would be worse than
    UNKNOWN (rule 4). Returns the matched Candidate or None; never raises.
    """
    if client is None or profile is None:
        return None
    try:
        name = _get(profile, "name", default=None)
        if not name or not str(name).strip():
            return None
        address = _get(profile, "physical_address", default=None)
        query = f"{name} {address}".strip() if address else str(name)
        candidates = client.search_text(query, max_results=max_results) or []

        from .peer_match import _domain, normalize_text
        own_site = (_get(profile, "website", default=None)
                    or _get(profile, "url", default=None)
                    or _get(profile, "source_url", default=None))
        own_domain = _domain(own_site) if own_site else None
        if own_domain:
            for c in candidates:
                if c.website and _domain(c.website) == own_domain:
                    return c
        norm_name = normalize_text(str(name))
        for c in candidates:
            if c.name and normalize_text(c.name) == norm_name:
                return c

        # Cross-script fallback (measured on Qasr Elkbabgi): the query IS the subject's
        # exact scraped name, but the Places listings are in another SCRIPT (Latin
        # profile name vs Arabic «قصر الكبابجي») with no website — so both grounded
        # matches above miss a true positive. Accept ONLY when >=2 returned candidates
        # are all the SAME brand (mutual containment of normalized names — branches/
        # variants of one business); ambiguity (different businesses) -> None, honest.
        named = [c for c in candidates if c.name and normalize_text(c.name)]
        if len(named) >= 2:
            cores = [normalize_text(c.name) for c in named]
            core = min(cores, key=len)
            if len(core) >= 4 and all(core in n for n in cores):
                return max(named, key=lambda c: c.review_count or 0)
        return None
    except Exception:  # noqa: BLE001 — a lookup failure must never break the SWOT
        return None