"""BrandCreativeDNA — learn a brand's REAL visual design language from its own creatives.

Owner's insight: the poster looked like a fixed template because we only ever fed the
model COLORS + fonts. The fix is to let the model SEE the brand's actual posters/ads and
reverse-engineer HOW they think visually — composition, hierarchy, typographic character,
imagery, signature moves — then design each new creative in that language (different every
time, unmistakably on-brand).

Pipeline (once per brand, cached):
  1) HARVEST  — image-search the brand's real marketing creatives (Serper images) + reuse
                its scraped on-page photos.
  2) UNDERSTAND — ONE multimodal Gemini 2.5 Pro call that SEES those creatives and emits a
                structured `BrandCreativeDNA` (the brand's design "how", not just its hex).
  3) PERSIST  — save the DNA so the poster/reel read it instead of re-deriving每 run.

GROUNDING / HONESTY: the DNA is pure DESIGN judgement over what the model SEES — it states
no factual claims (facts stay in the validated profile). We LEARN design principles from the
brand's creatives; we never reproduce them. Side-effect free (caller + provider injected;
no .env / os.environ mutation), same discipline as brand_book.py / poster/brand_research.py.
Degrades gracefully: no provider -> website photos only; no caller -> a profile-only stub;
no images -> text-only note. Never raises for ordinary failures.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from brand.brand_book import _fetch_images, _fv
from scraper.url_utils import _registrable_domain, same_registrable_host


# ---------------------------------------------------------------------
# Public schema
# ---------------------------------------------------------------------

class BrandCreativeDNA(BaseModel):
    """The brand's learned visual design language — read by the poster/reel art-director."""
    business_name: str
    used_vision: bool = False
    references_seen: list[str] = Field(default_factory=list)   # the creative URLs analyzed
    # Brand-ownership filter accounting (so the before/after is visible per brand): how many
    # search candidates came back vs how many passed the STRICT brand-owned filter, and how
    # many analyzed refs are the brand's own scraped site images (tier 2). If most brands rely
    # only on site images, that's a signal to add verified social-API harvesting — not a failure.
    harvested_total: int = 0
    kept_after_brand_filter: int = 0
    site_images_used: int = 0

    layout_philosophy: str = ""        # how they arrange a creative overall
    composition_patterns: str = ""     # framing, balance, focal points, grid habits
    typographic_character: str = ""    # weight/case/scale/contrast of their type
    color_usage: str = ""              # HOW the palette is used (not just which hex)
    imagery_style: str = ""            # photo vs graphic, subjects, treatment
    mood: str = ""
    motifs: str = ""                   # recurring shapes/devices (e.g. a purple block)
    text_density: str = ""             # minimal vs busy; how much copy
    signature_moves: str = ""          # the recognizable "that's so THEM" things
    do_list: list[str] = Field(default_factory=list)
    dont_list: list[str] = Field(default_factory=list)
    note: Optional[str] = None


# LLM structured-output model (no meta fields; strict-mode safe — no numeric ranges).
class _DnaResponse(BaseModel):
    layout_philosophy: str
    composition_patterns: str
    typographic_character: str
    color_usage: str
    imagery_style: str
    mood: str
    motifs: str
    text_density: str
    signature_moves: str
    do_list: list[str]
    dont_list: list[str]


# ---------------------------------------------------------------------
# 1) Harvest — the brand's real creatives
# ---------------------------------------------------------------------

def _host(url: str) -> str:
    try:
        return (urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
    except Exception:
        return ""


def harvest_creative_urls(
    brand_name: str, *, brand_domain: str = "", num: int = 10, api_key: Optional[str] = None,
) -> list[dict]:
    """Image-search the brand's real creatives via Serper /images. Returns CANDIDATES —
    each `{image_url, page_host, page_link}` — so the caller can verify brand OWNERSHIP from
    the PAGE the image sits on (the image CDN URL alone is opaque and un-attributable). The
    query is constrained to the brand NAME (as a phrase) + its DOMAIN + 'ad/campaign' words,
    NOT a generic sector word. Best-effort ([] when no key); resilient fetcher; never raises."""
    key = api_key or os.environ.get("SERPER_API_KEY")
    if not key or not (brand_name or "").strip():
        return []
    from scraper.net import post_json

    queries = [f'"{brand_name}" ad campaign poster creative']
    queries.append(f'"{brand_name}" {brand_domain} advertising'.strip() if brand_domain
                   else f'"{brand_name}" social media ad creative')

    out: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        data = post_json(
            "https://google.serper.dev/images",
            {"q": q, "num": num},
            key="serper:images",           # group the breaker for the images endpoint
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
        ) or {}
        for it in (data.get("images") or []):
            img = (it.get("imageUrl") or it.get("imageURL") or "").strip()
            if not img.startswith(("http://", "https://")) or img in seen:
                continue
            page = (it.get("link") or it.get("source") or "").strip()
            host = (it.get("domain") or "").strip().lower() or _host(page)
            seen.add(img)
            out.append({"image_url": img, "page_host": host, "page_link": page})
        if len(out) >= num * 2:
            break
    return out


# ---------------------------------------------------------------------
# Brand-ownership filter (STRICT, tiered — the grounded-image principle)
# ---------------------------------------------------------------------

def _brand_root_url(profile: dict) -> str:
    """The brand's own site URL (final_url preferred) for registrable-domain matching."""
    return _fv(profile, "final_url") or _fv(profile, "source_url") or ""


def _brand_social_profiles(profile: dict) -> list[tuple[str, str]]:
    """(host, handle_path) per known brand social profile — so a social-hosted image is
    confirmed to be on THE BRAND's page (handle in the link), not just any page on that
    platform (which is what reusing the FB/IG CDN blindly would wrongly accept)."""
    out: list[tuple[str, str]] = []
    for s in (profile.get("social_presence") or []):
        url = (s.get("url") if isinstance(s, dict) else None) or ""
        if not url:
            continue
        p = urlparse(url if "://" in url else "https://" + url)
        host = (p.hostname or "").lower()
        path = (p.path or "").rstrip("/").lower()
        if host:
            out.append((host, path))
    return out


def _is_brand_owned(cand: dict, brand_url: str, social: list[tuple[str, str]]) -> bool:
    """STRICT: the image's PAGE must be the brand's OWN site, OR the brand's OWN social
    profile (handle confirmed in the link). Anything else — a random domain, an aggregator,
    stock, or a CDN we cannot attribute — is NOT brand-owned and is rejected. A grounded,
    weaker DNA beats a confident fabricated one (the same principle as the copy gate)."""
    host = (cand.get("page_host") or "").strip().lower()
    link = (cand.get("page_link") or "").lower()
    if not host:
        return False
    if brand_url and same_registrable_host(host, brand_url):
        return True
    for sp_host, sp_path in social:
        if same_registrable_host(host, sp_host) and sp_path and sp_path in link:
            return True
    return False


def _brand_photo_urls(profile: dict, limit: int) -> list[str]:
    vis = (profile or {}).get("visual") or {}
    urls: list[str] = []
    for c in (vis.get("content_images") or []):
        src = c.get("src") if isinstance(c, dict) else c
        if src and src not in urls:
            urls.append(src)
    return urls[:limit]


# ---------------------------------------------------------------------
# 2) Build
# ---------------------------------------------------------------------

def build_creative_dna(
    profile: dict[str, Any],
    *,
    caller: Any = None,
    search_provider: Any = None,           # accepted for symmetry; harvest uses SERPER_API_KEY
    serper_api_key: Optional[str] = None,
    max_refs: int = 8,
    _image_fetcher=_fetch_images,          # injectable for tests (no network)
    _harvester=harvest_creative_urls,      # injectable for tests (no network)
) -> BrandCreativeDNA:
    """Learn the BrandCreativeDNA for one profile. `caller` should be a MULTIMODAL Gemini
    caller (Pro — this is the complex 'understand the design' step). Never raises."""
    name = _fv(profile, "name") or "the brand"
    brand_url = _brand_root_url(profile)
    brand_dom = _registrable_domain(brand_url) or ""
    social = _brand_social_profiles(profile)

    # HARVEST -> STRICT brand-ownership filter (tiered, like the copy gate). Only the brand's
    # OWN creatives count; doubtful search hits are REJECTED outright (never fill a slot).
    raw = _harvester(name, brand_domain=brand_dom, num=max_refs, api_key=serper_api_key) or []
    cands = [c if isinstance(c, dict) else {"image_url": c, "page_host": _host(c), "page_link": c}
             for c in raw]
    harvested_total = len(cands)
    brand_ads: list[str] = []
    for c in cands:
        u = (c.get("image_url") or "").strip()
        if u and u not in brand_ads and _is_brand_owned(c, brand_url, social):
            brand_ads.append(u)
    kept = len(brand_ads)

    # TIER ORDER: brand-owned ADS first, THEN the brand's own scraped SITE imagery
    # (content_images — already verified theirs by the scraper). Nothing else enters; if
    # neither exists, the DNA is a stub (honest UNKNOWN) rather than built on doubtful images.
    ordered = list(brand_ads)
    for u in _brand_photo_urls(profile, max_refs):
        if u not in ordered:
            ordered.append(u)
    creative_urls = ordered[:max_refs]
    site_used = sum(1 for u in creative_urls if u not in brand_ads)
    images = _image_fetcher(creative_urls) if creative_urls else []
    seen_urls = [u for (u, _b, _m) in images]
    _counts = dict(harvested_total=harvested_total, kept_after_brand_filter=kept,
                   site_images_used=site_used)

    if caller is None:
        return BrandCreativeDNA(
            business_name=name, used_vision=False, references_seen=seen_urls,
            note="no caller: profile-only DNA stub (no vision)", **_counts,
        )
    if not images:
        return BrandCreativeDNA(
            business_name=name, used_vision=False, references_seen=[],
            note="no brand-owned creatives passed the filter: no visual DNA built (honest UNKNOWN)",
            **_counts,
        )

    try:
        from poster.art_director import _persona_lines
        persona = _persona_lines(profile)
    except Exception:
        persona = ""

    system = (
        "You are a world-class advertising ART DIRECTOR doing a forensic teardown. You are "
        "shown a brand's REAL marketing creatives (posters / ads / social), in order. "
        "Reverse-engineer their VISUAL DESIGN LANGUAGE — how this brand THINKS visually, so a "
        "new creative could be designed that is unmistakably theirs yet fresh.\n"
        "Describe, concretely and specifically (not generic):\n"
        "- layout_philosophy: how they arrange a creative (where the logo / headline / subject sit).\n"
        "- composition_patterns: framing, balance, focal point, grid/diagonal habits, cropping.\n"
        "- typographic_character: weight, case, scale jumps, contrast, alignment of their type.\n"
        "- color_usage: HOW the palette is deployed (dominant field, accents, where) — not just hex.\n"
        "- imagery_style: photography vs graphic, subjects, lighting, treatment.\n"
        "- mood; motifs (recurring shapes/devices, e.g. a solid brand-colour block or a wave);\n"
        "- text_density (minimal vs busy); signature_moves (the recognizable 'that is so THEM').\n"
        "- do_list / dont_list: concrete rules for a NEW on-brand poster.\n"
        "Judge ONLY what you SEE. Make no factual claims about the company. Be specific to THIS "
        "brand — never a generic design-textbook answer."
    )
    user = (
        f"Brand: {name}\n"
        + (f"Profile (verbatim, for context only):\n{persona}\n" if persona else "")
        + f"\nReal creatives shown to you (by index 0..{len(seen_urls) - 1}):\n"
        + "\n".join(f"[{i}] {u}" for i, u in enumerate(seen_urls))
    )

    try:
        resp, _u = caller(
            system, user, _DnaResponse, group_name="creative_dna",
            images=[(b, m) for (_u2, b, m) in images],
        )
    except Exception as exc:  # noqa: BLE001
        return BrandCreativeDNA(
            business_name=name, used_vision=False, references_seen=seen_urls,
            note=f"vision call failed ({type(exc).__name__})", **_counts,
        )

    return BrandCreativeDNA(
        business_name=name, used_vision=True, references_seen=seen_urls, **_counts,
        layout_philosophy=resp.layout_philosophy.strip(),
        composition_patterns=resp.composition_patterns.strip(),
        typographic_character=resp.typographic_character.strip(),
        color_usage=resp.color_usage.strip(),
        imagery_style=resp.imagery_style.strip(),
        mood=resp.mood.strip(),
        motifs=resp.motifs.strip(),
        text_density=resp.text_density.strip(),
        signature_moves=resp.signature_moves.strip(),
        do_list=[s.strip() for s in (resp.do_list or []) if s.strip()][:8],
        dont_list=[s.strip() for s in (resp.dont_list or []) if s.strip()][:8],
    )


# ---------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------

def save_creative_dna(dna: BrandCreativeDNA, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dna.model_dump_json(indent=2), encoding="utf-8")
    return p


def load_creative_dna(path: str | Path) -> BrandCreativeDNA:
    return BrandCreativeDNA.model_validate_json(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------
# CLI:  python -m brand.creative_dna <business_profile.json> [--out path]
# ---------------------------------------------------------------------

def main() -> int:
    import argparse
    import json
    import sys

    for _s in (sys.stdout, sys.stderr):           # Windows cp1252 -> Arabic-safe
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass

    ap = argparse.ArgumentParser(prog="brand.creative_dna",
                                 description="Learn a brand's visual design DNA from its real creatives.")
    ap.add_argument("profile", help="path to a business_profile.json")
    ap.add_argument("--out", default=None, help="output DNA json path")
    args = ap.parse_args()

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))

    caller = None
    try:
        from business_profile.llm import default_caller
        caller = default_caller(strong=True)      # Gemini 2.5 Pro — the complex vision step
    except Exception:
        caller = None

    print("[1/2] harvesting the brand's real creatives + understanding them (vision)...")
    dna = build_creative_dna(profile, caller=caller)
    print(f"      used_vision={dna.used_vision}  references_seen={len(dna.references_seen)}")
    print(f"      brand-filter: harvested={dna.harvested_total} "
          f"kept_brand_owned={dna.kept_after_brand_filter} site_images_used={dna.site_images_used}")
    if dna.note:
        print(f"      note: {dna.note}")

    print("\n=== BrandCreativeDNA:", dna.business_name, "===")
    for f in ("layout_philosophy", "composition_patterns", "typographic_character",
              "color_usage", "imagery_style", "mood", "motifs", "text_density",
              "signature_moves"):
        v = getattr(dna, f)
        if v:
            print(f"- {f}: {v}")
    if dna.do_list:
        print("- DO:", " | ".join(dna.do_list))
    if dna.dont_list:
        print("- DON'T:", " | ".join(dna.dont_list))

    out = args.out or f"outputs/brandbooks/{(dna.business_name or 'brand').lower().replace(' ', '_')}_dna.json"
    save_creative_dna(dna, out)
    print("\nDONE ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
