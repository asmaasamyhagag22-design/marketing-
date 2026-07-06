"""
full_run.py -- end-to-end: URL -> BusinessProfile -> competitors -> matrix -> SWOT.

Lives in competitor/. Run from the PROJECT ROOT. Both styles work:

    python -m competitor.full_run https://some-clinic.com
    python competitor/full_run.py  https://some-clinic.com
    python competitor/full_run.py  https://some-clinic.com --no-themes

Needs in your .env (this script loads it before any stage runs):
    GOOGLE_MAPS_API_KEY   Places discovery            (you confirmed: working)
    OPENAI_API_KEY        subject BusinessProfile      (the build_profile step)
    ANTHROPIC_API_KEY     review-theme extraction      (optional; --no-themes skips)

Output is forced to UTF-8 so Arabic review text won't crash the Windows console.
"""
import argparse
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Make the project root importable whether launched as
#   python -m competitor.full_run ...   (root already on sys.path)
# or
#   python competitor/full_run.py ...   (only competitor/ is on sys.path by default)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_env():
    """Load KEY=VALUE pairs from the project-root .env into os.environ (only
    for keys not already set in the shell), so OpenAI/Anthropic/Google all see
    their keys before any stage runs. Dependency-free."""
    for folder in (_ROOT, *_ROOT.parents, Path.cwd()):
        env_path = folder / ".env"
        if not env_path.is_file():
            continue
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    name, _, val = line.partition("=")
                    name = name.strip()
                    if name:
                        os.environ.setdefault(name, val.strip().strip('"').strip("'"))
        except OSError:
            continue
        break  # first .env found wins


_load_env()  # must happen before importing/using anything that reads keys

from scraper import scrape
from business_profile.build import build_profile
from business_profile.llm import OpenAICaller
from competitor import (
    PlacesClient,
    route_discovery,
    build_matrix,
    AnthropicThemeExtractor,
    synthesize_swot,
    format_swot,
)
from competitor.swot import unique_insight_texts


def scrape_fn(url):
    """What build_matrix calls to scrape each benchmark competitor's site."""
    manifest, _ = scrape(url)
    return manifest


def scrape_yielded_nothing(manifest) -> bool:
    """True when the crawl fetched ZERO usable pages — the site blocked us, was unreachable, or had
    an invalid cert. Building a profile from an empty manifest yields a hollow, ungrounded result;
    the caller must surface a clear failure instead of proceeding on garbage."""
    return len(getattr(manifest, "pages", []) or []) == 0


def _make_caller():
    """build_profile needs an explicit LLM caller. Build the OpenAI one,
    tolerating either OpenAICaller() or OpenAICaller(model=...)."""
    try:
        return OpenAICaller()
    except TypeError:
        return OpenAICaller(model="gpt-4o-mini")


def _as_profile(built):
    """build_profile may return the BusinessProfile directly OR a BuildResult
    wrapper -- handle both without guessing which."""
    for attr in ("profile", "business_profile"):
        if hasattr(built, attr):
            return getattr(built, attr)
    return built


def _category_str(profile):
    """category may be a plain enum/str or a wrapped field with .value."""
    cat = getattr(profile, "category", None)
    val = getattr(cat, "value", cat)              # unwrap a field-with-value
    return getattr(val, "value", val)             # unwrap an enum


def main():
    _load_env()

    ap = argparse.ArgumentParser(description="URL -> profile -> competitors -> SWOT")
    ap.add_argument("url", help="subject business URL (use one with a REAL website)")
    ap.add_argument("--no-themes", action="store_true",
                    help="skip the Anthropic review-theme extraction step")
    ap.add_argument("--json", action="store_true",
                    help="print the SWOT as JSON to stdout (progress goes to stderr)")
    ap.add_argument("--out", default=None,
                    help="path to write the full result JSON (profile + competitors + "
                         "SWOT). Default: result.json inside the scrape's output folder.")
    args = ap.parse_args()

    # Progress -> stderr when --json, so stdout stays valid, pipeable JSON.
    def say(msg=""):
        print(msg, file=sys.stderr if args.json else sys.stdout)

    if not os.getenv("OPENAI_API_KEY"):
        print("!! OPENAI_API_KEY not found (not in shell env, not in project .env).", file=sys.stderr)
        print("   add it to your .env (next to GOOGLE_MAPS_API_KEY) and re-run.", file=sys.stderr)
        return 2

    say("[1/5] scraping subject site: %s" % args.url)
    manifest, scrape_dir = scrape(args.url)

    # A 0-page crawl (blocked / unreachable / bad cert) would otherwise build a hollow profile and a
    # garbage dashboard that LOOKS successful. Fail loudly instead so the studio shows a clear reason.
    if scrape_yielded_nothing(manifest):
        fails = "; ".join(str(f) for f in (getattr(manifest, "failures", []) or [])[:2])
        print("!! could not read this site — 0 pages scraped"
              + (f" ({fails})" if fails else "")
              + ". It may block crawlers, be down, or have an invalid certificate.", file=sys.stderr)
        return 3

    say("[2/5] building BusinessProfile (OpenAI extraction)...")
    caller = _make_caller()
    profile = _as_profile(build_profile(manifest, caller, use_rag=True))
    if not hasattr(profile, "category"):
        print("!! build_profile() didn't return something with a .category field.", file=sys.stderr)
        return 1
    say("      subject category = %s" % _category_str(profile))

    say("[3/5] discovering competitors (adaptive router)...")
    client = PlacesClient()
    from competitor.web_discovery import default_web_engine
    web_engine = default_web_engine()
    if web_engine is not None:
        say("      web discovery: %s (search peers for ECOMMERCE/HYBRID)" % web_engine.name)
    # Adaptive routing: LOCAL->Places, ECOMMERCE->SERP web engine (when a search
    # key is set), HYBRID->both, UNKNOWN->skip. Never raises; an empty result
    # degrades to a standalone SWOT below instead of stopping the run.
    result = route_discovery(profile, places_client=client, manifest=manifest,
                             web_engine=web_engine)
    n = len(result.competitors)
    scrapable = sum(1 for c in result.competitors
                    if getattr(c, "has_scrapable_site", False))
    say("      competitors=%d  scrapable_benchmarks=%d" % (n, scrapable))
    for note in getattr(result, "notes", []) or []:
        say("   note: %s" % note)
    if n == 0:
        say("   -> no competitors; continuing in STANDALONE mode (profile-only SWOT).")

    say("[4/5] building comparison matrix (scrapes %d benchmark site(s))..." % scrapable)
    # The subject's OWN Places listing (rating/volume/price) — without it every
    # Places gap is "n/a" and market-position Threats can never fire. Grounded
    # match (domain / exact name) only; None on no-match, never raises.
    from competitor import find_subject_places
    subject_places = find_subject_places(profile, client)
    if subject_places is not None:
        say("      subject Places listing: %s (rating=%s, reviews=%s)" % (
            subject_places.name, subject_places.rating, subject_places.review_count))
    matrix = build_matrix(
        manifest,                 # reuse the subject's manifest -> no re-scrape of subject
        result.competitors,
        scrape_fn=scrape_fn,
        subject_places=subject_places,
    )

    themes = []
    if args.no_themes:
        say("[5/5] skipping review themes (--no-themes)")
    else:
        say("[5/5] extracting grounded review themes (Anthropic)...")
        themes = AnthropicThemeExtractor()(result.competitors)
        try:
            say("      kept %d grounded theme(s)" % len(themes))
        except TypeError:
            pass

    # Serialize the profile ONCE — the SWOT now mines it for brand-level strengths (value props +
    # proof, Ledger-gated) and TOWS reuses it downstream.
    profile_dict = (profile.model_dump(mode="json")
                    if hasattr(profile, "model_dump") else (profile if isinstance(profile, dict) else None))

    # On-topic market trends -> brand-level Opportunities/Threats (esp. for online brands with no
    # Places peers). Best-effort: any failure (offline / no key) degrades to [] — never blocks.
    trends: list = []
    try:
        from trends import keywords_from_profile, top_trends_bounded
        kws = keywords_from_profile(profile_dict or {})
        if kws:                              # HARD 12s deadline — a hung source never blocks analyze
            trends = top_trends_bounded(kws, timeout_s=12.0, require_match=True, top_k=6)
    except Exception:
        trends = []

    swot = synthesize_swot(matrix, themes=themes,
                           unique_insights=unique_insight_texts(profile),
                           profile=profile_dict, trends=trends)

    # TOWS synthesis (strategies + priority actions) from the cited SWOT —
    # deterministic here (no extra LLM cost on the CLI path); never raises.
    from competitor import build_tows
    tows = build_tows(swot, caller=None, profile=profile_dict)

    # --- consolidated result -> output file ------------------------------------
    # Everything the run produced, grounded: the subject profile, the discovered
    # competitors (with their why_selected provenance), and the cited SWOT. The
    # profile is pydantic (model_dump); competitors + SWOT are dataclasses (asdict).
    import dataclasses
    import json as _json
    from datetime import datetime, timezone

    swot_json = dataclasses.asdict(swot)            # mode + 4 quadrants + notes
    result_doc = {
        "subject_url": args.url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "subject_category": _category_str(profile),
        "competitor_count": n,
        "scrapable_benchmarks": scrapable,
        "discovery_notes": list(getattr(result, "notes", []) or []),
        "profile": (
            profile.model_dump(mode="json")
            if hasattr(profile, "model_dump") else str(profile)
        ),
        "competitors": [dataclasses.asdict(c) for c in result.competitors],
        "swot": swot_json,
        "tows": dataclasses.asdict(tows),
    }

    out_path = Path(args.out) if args.out else (Path(scrape_dir) / "result.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        _json.dumps(result_doc, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    say("\n[ok] wrote full result (profile + competitors + SWOT) -> %s"
        % out_path.resolve())

    if args.json:
        payload = dict(swot_json)
        payload["competitor_count"] = n
        print(_json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("\n" + "=" * 72)
        print(format_swot(swot))
        print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())