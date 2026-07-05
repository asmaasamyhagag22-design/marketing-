"""Brand research via deep web search — FRESH, SOURCED facts before generation.

Why this exists: the poster headline was a single VERBATIM line from the homepage
scrape, so the same brand produced the same copy every time. This module runs a web
search about the brand and lets a powerful model turn the REAL search snippets into
(a) a pool of sourced facts and (b) several distinct ad-copy ANGLES — so each
generation can use a different, fresher line.

ZERO-HALLUCINATION CONTRACT (this must never erode the product's whole premise):
  * Every fact CARRIES its source URL (provenance). Facts come only from the search
    snippets / the scraped profile — never invented.
  * An ad angle may be an evocative PARAPHRASE, but any HARD claim (numbers, awards,
    "presidential initiative", certifications) must be supported by a cited snippet;
    the model flags `asserts_hard_fact` so the caller can prefer safe angles.
  * No provider / no results -> used=False and EMPTY angles; the caller falls back to
    the verbatim profile headline. Never fabricated.

Side-effect free: never loads .env or mutates os.environ (entry points load .env and
inject the provider/caller). Mirrors scraper/deep_search.py's discipline.
"""
from __future__ import annotations

import random
from typing import Any, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------

class BrandFact(BaseModel):
    text: str
    source_url: str = ""


class BrandAngle(BaseModel):
    """One ad-copy angle. `headline` is what goes on the poster; `grounded_in` is the
    source URL (or 'profile') it derives from; `asserts_hard_fact` warns the caller
    that the line states a concrete claim (prefer angles a human can quickly verify)."""
    headline: str
    subheadline: Optional[str] = None
    grounded_in: str = "profile"
    asserts_hard_fact: bool = False


class BrandResearch(BaseModel):
    used: bool = False
    provider: Optional[str] = None
    query: Optional[str] = None
    facts: list[BrandFact] = []
    angles: list[BrandAngle] = []
    note: Optional[str] = None


# ---------------------------------------------------------------------
# LLM structured-output models (no numeric/range constraints -> strict-mode safe)
# ---------------------------------------------------------------------

class _Fact(BaseModel):
    text: str
    source_url: str


class _Angle(BaseModel):
    headline: str
    subheadline: str          # "" when none
    grounded_in: str          # a source URL, or "profile"
    asserts_hard_fact: bool


class _ResearchResponse(BaseModel):
    facts: list[_Fact]
    angles: list[_Angle]


# ---------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------

def research_brand(
    business_name: str,
    *,
    homepage_url: str = "",
    persona: str = "",
    trend_context: str = "",
    provider: Any = None,
    caller: Any = None,
    results_per_query: int = 8,
    max_facts: int = 6,
    max_angles: int = 6,
) -> BrandResearch:
    """Search the web for the brand and synthesize SOURCED facts + ad angles.

    `provider` is a competitor.search_providers SearchProvider (resolved by default
    from the environment). `caller` is a business_profile.llm Caller (a powerful model
    is recommended). Returns BrandResearch — always honest about provenance, never
    raises for ordinary failures.
    """
    if not business_name or not business_name.strip():
        return BrandResearch(used=False, note="no business name")

    if provider is None:
        try:
            from competitor.search_providers import get_default_search_provider
            provider = get_default_search_provider()
        except Exception:
            provider = None
    if provider is None:
        return BrandResearch(used=False, note="no search provider configured")

    brand = business_name.strip()
    # A few real-context angles: the brand itself, what it is, and recent signal.
    queries = [brand, f"{brand} about", f"{brand} news"]
    hits: list[Any] = []
    seen_links: set[str] = set()
    for q in queries:
        try:
            for h in (provider.search(q, num=results_per_query) or []):
                link = getattr(h, "link", "") or ""
                if link and link not in seen_links:
                    seen_links.add(link)
                    hits.append(h)
        except Exception:
            continue

    if not hits:
        return BrandResearch(
            used=True, provider=getattr(provider, "name", "search"),
            query=" | ".join(queries), note="search returned no results",
        )

    # No LLM -> still return the raw snippets as sourced facts (honest, no copy).
    if caller is None:
        facts = [
            BrandFact(text=(getattr(h, "snippet", "") or getattr(h, "title", "") or "").strip(),
                      source_url=getattr(h, "link", "") or "")
            for h in hits[:max_facts]
            if (getattr(h, "snippet", "") or getattr(h, "title", ""))
        ]
        return BrandResearch(
            used=True, provider=getattr(provider, "name", "search"),
            query=" | ".join(queries), facts=facts,
            note="no caller: raw sourced snippets only (no crafted angles)",
        )

    # Build the numbered, sourced snippet block for the model.
    lines = []
    for i, h in enumerate(hits[:results_per_query * 2], start=1):
        title = (getattr(h, "title", "") or "").strip()
        snip = (getattr(h, "snippet", "") or "").strip()
        url = getattr(h, "link", "") or ""
        if not (title or snip):
            continue
        lines.append(f"[{i}] {title} — {snip} (source: {url})")
    snippet_block = "\n".join(lines)

    system = (
        "You are a brand researcher AND advertising copywriter. You are given REAL web "
        "search results about a brand (each with a source URL) and its scraped profile.\n"
        "TASK 1 — facts: extract up to "
        f"{max_facts} notable, CONCRETE facts about the brand. Each fact must be copied "
        "or closely paraphrased from a specific search snippet, and you MUST set its "
        "source_url to that snippet's URL. Do NOT invent facts that are not in the "
        "snippets or profile.\n"
        "TASK 2 — angles: write up to "
        f"{max_angles} DISTINCT short ad headline angles (each <= 60 characters), each "
        "with an optional one-line subheadline. Make them genuinely different from each "
        "other (different hook, benefit, or emotion). For each angle set grounded_in to "
        "the source URL it draws from (or 'profile'), and asserts_hard_fact=true if the "
        "headline states a concrete verifiable claim (a number, award, official status "
        "like 'presidential initiative', certification). If you are unsure a hard claim "
        "is supported, keep the angle evocative and set asserts_hard_fact=false.\n"
        "If a CURRENT TREND below genuinely fits the brand, you MAY tie ONE angle to it "
        "(timely > generic) — but NEVER force an irrelevant trend or fabricate a link.\n"
        "Write in the brand's own language (Arabic stays Arabic). Never fabricate."
    )
    user = (
        f"Brand: {brand}\n"
        + (f"Homepage: {homepage_url}\n" if homepage_url else "")
        + (f"\nScraped profile (verbatim):\n{persona}\n" if persona else "")
        + (f"\nCurrent trends you MAY tie into (only if it genuinely fits):\n{trend_context}\n"
           if trend_context else "")
        + f"\nReal web search results:\n{snippet_block}\n"
    )

    try:
        resp, _usage = caller(system, user, _ResearchResponse, group_name="brand_research")
    except Exception as exc:
        # Degrade to raw snippets — still real and sourced.
        facts = [
            BrandFact(text=(getattr(h, "snippet", "") or "").strip(),
                      source_url=getattr(h, "link", "") or "")
            for h in hits[:max_facts] if getattr(h, "snippet", "")
        ]
        return BrandResearch(
            used=True, provider=getattr(provider, "name", "search"),
            query=" | ".join(queries), facts=facts,
            note=f"caller failed ({type(exc).__name__}); raw snippets only",
        )

    valid_sources = seen_links | {"profile"}
    facts = [
        BrandFact(text=f.text.strip(), source_url=f.source_url.strip())
        for f in (resp.facts or [])[:max_facts]
        if f.text and f.text.strip()
    ]
    angles: list[BrandAngle] = []
    for a in (resp.angles or [])[:max_angles]:
        head = (a.headline or "").strip()
        if not head:
            continue
        # Keep provenance honest: a source must be one the SEARCH ACTUALLY RETURNED
        # (or 'profile'); anything else — including a real-LOOKING http URL the model
        # INVENTED — is downgraded to 'profile', so a hallucinated citation can't launder
        # an unsourced hard claim past pick_angle's prefer_safe gate onto the poster.
        src = a.grounded_in.strip() if a.grounded_in else "profile"
        if src not in valid_sources:
            src = "profile"
        angles.append(BrandAngle(
            headline=head,
            subheadline=(a.subheadline or "").strip() or None,
            grounded_in=src,
            asserts_hard_fact=bool(a.asserts_hard_fact),
        ))

    return BrandResearch(
        used=True,
        provider=getattr(provider, "name", "search"),
        query=" | ".join(queries),
        facts=facts,
        angles=angles,
        note=None if angles else "model returned no angles",
    )


def _is_reputable_source(url: str) -> bool:
    """Thin alias for the shared web-source reputability gate. The logic now lives in
    `grounding.is_reputable_web_source` so the ledger enforces it for EVERY gate
    (concept/calendar/TOWS/reel) at build time, not just here in pick_angle."""
    from grounding import is_reputable_web_source
    return is_reputable_web_source(url)


def _ledger_keeps_angle(angle: "BrandAngle", ledger: Any) -> bool:
    """The Evidence-Ledger gate for one ad angle (used when a ledger is supplied).

    Reject if any FALSIFIABLE claim in the angle (number/year, certification/award, or a
    ranking/comparison) is UNSOURCED. A claim backed only by a WEB-tier source (a search
    snippet, not the brand's own site) is accepted only if that source is reputable —
    'source = snippet' is weaker than 'source = the brand site' (owner's rule). Pure
    paraphrase (no falsifiable claim) always passes."""
    text = " . ".join(filter(None, [angle.headline, angle.subheadline]))
    verdicts = ledger.audit_text(text)
    for v in verdicts:
        if not v.sourced:
            return False                                   # an unverifiable claim -> drop
        res = v.resolution
        if res is not None and res.tier == "web" and not _is_reputable_source(res.source_url):
            return False                                   # backed only by a junk snippet -> drop
    return True


def pick_angle(
    research: Optional[BrandResearch],
    fallback_headline: str,
    *,
    variation: Optional[int] = None,
    prefer_safe: bool = True,
    ledger: Any = None,
) -> tuple[str, Optional[str], str]:
    """Choose one angle for this generation. Returns (headline, subheadline, provenance).

    Rotates across angles by `variation` (deterministic) or randomly (fresh each run
    when variation is None). When `prefer_safe`, angles that assert a hard claim are
    only used if they cite a real source URL. When a grounding `ledger` is supplied
    (built from the profile + the research facts), every angle is additionally verified
    against REAL evidence — any unsourced falsifiable claim, or a claim backed only by a
    non-reputable web snippet, is dropped (the Evidence-Ledger gate, unifying the coarse
    prefer_safe self-report onto the actual evidence). Falls back to the verbatim profile
    headline when no angle survives — never lose grounding for the sake of novelty.
    """
    angles = list(research.angles) if research else []
    if prefer_safe and angles:
        # Cheap first pass: drop hard-claim angles that lack a real source URL.
        angles = [
            a for a in angles
            if (not a.asserts_hard_fact) or (a.grounded_in or "").startswith("http")
        ]
    if ledger is not None and angles:
        # Real evidence check (+ web-source reputability) on what survived prefer_safe.
        angles = [a for a in angles if _ledger_keeps_angle(a, ledger)]

    if not angles:
        return fallback_headline, None, "profile"

    idx = random.randrange(len(angles)) if variation is None else variation % len(angles)
    chosen = angles[idx]
    return chosen.headline, chosen.subheadline, chosen.grounded_in
