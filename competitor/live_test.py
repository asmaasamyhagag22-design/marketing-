"""Live end-to-end test of the REAL Places path (makes real API calls).

Unlike smoke_test.py (offline, scoring only), this hits Google:
  geocode -> searchNearby -> select -> fetch reviews.

Run it once to confirm your key + enabled APIs + field masks all work, BEFORE
building the matrix/SWOT on top.

    # cheapest first: search only, no review fetch
    python -m competitor.live_test --no-reviews

    # full run including reviews
    python -m competitor.live_test

    # override the test subject from the CLI
    python -m competitor.live_test --category clinic --address "Road 9, Maadi, Cairo, Egypt"

Edit DEFAULT_PROFILE below to point at a real area/category you want to test.
The "name" is only used to drop the subject from results, so a placeholder is
fine. The address just needs to geocode to a real point so the nearby search
has a real center.
"""

from __future__ import annotations

import argparse

try:
    from .places_client import PlacesClient, PlacesError
    from .discovery import discover_competitors
except ImportError:  # pragma: no cover
    from places_client import PlacesClient, PlacesError  # type: ignore
    from discovery import discover_competitors            # type: ignore


# A real Cairo location as the search center + a category. Swap freely.
DEFAULT_PROFILE = {
    "name": "Test Subject Clinic (placeholder)",
    "category": "clinic",
    "offerings": ["laser hair removal", "acne treatment", "skin care", "dermatology"],
    "audience_type": "mid-market",
    "audience_confidence": 0.8,
    "languages": ["ar", "en"],
    "physical_address": "Road 9, Maadi, Cairo, Egypt",
    # "lat": 29.9602, "lng": 31.2569,   # optionally skip geocoding by giving coords
    "review_count": None,                 # subject's own Places review count, if known
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category")
    ap.add_argument("--address")
    ap.add_argument("--radius", type=int, default=15000)
    ap.add_argument("--pool", type=int, default=20)
    ap.add_argument("--min-scrapable", type=int, default=2,
                    help="min scrapable benchmark peers to include for the matrix")
    ap.add_argument("--no-reviews", action="store_true")
    ap.add_argument("--debug", action="store_true",
                    help="always print the per-candidate filter audit")
    ap.add_argument("--require-website", action="store_true",
                    help="require a real website (OFF by default — Egyptian market is social-heavy)")
    args = ap.parse_args()

    profile = dict(DEFAULT_PROFILE)
    if args.category:
        profile["category"] = args.category
    if args.address:
        profile["physical_address"] = args.address
        profile.pop("lat", None)
        profile.pop("lng", None)

    try:
        client = PlacesClient()  # reads GOOGLE_MAPS_API_KEY
    except PlacesError as e:
        print("KEY/SETUP ERROR:", e)
        return

    print(f"Subject: {profile['category']} @ {profile.get('physical_address') or (profile.get('lat'), profile.get('lng'))}")
    print(f"radius={args.radius}m  pool={args.pool}  reviews={not args.no_reviews}\n")

    try:
        result = discover_competitors(
            profile, client,
            radius_m=args.radius,
            candidate_pool=args.pool,
            require_website=args.require_website,
            min_scrapable_benchmarks=args.min_scrapable,
            fetch_reviews=not args.no_reviews,
        )
    except PlacesError as e:
        print("PLACES API ERROR:", e)
        print("\nCommon causes:")
        print("  - Geocoding API not enabled on the key (REQUEST_DENIED)")
        print("  - Places API (New) not enabled, or billing not set up")
        print("  - a field-mask field name is wrong for your region")
        return

    print(f"considered={result.candidates_considered}  "
          f"passed_filters={result.candidates_passed_filters}  "
          f"selected={len(result.competitors)}  thin={result.thin_peer_set}")
    if result.notes:
        print("notes:")
        for n in result.notes:
            print("  -", n)
    print()

    # When the set is thin (or in --debug), show WHY each considered place
    # passed/failed the hard filters — so we fix the real bottleneck, not a guess.
    if result.audit and (args.debug or result.thin_peer_set):
        print("-- candidate audit (considered places, after the radius cap) --")
        for a in result.audit:
            verdict = "PASS" if a["passed"] else f"drop:{a['reason']}"
            site = "site" if a["website"] else "NO-site"
            name = (a["name"] or "")[:34]
            print(f"   [{verdict:>18}]  {name:<34} type={a['type']} "
                  f"reviews={a['reviews']} {site} {a['dist_km']}km")
        print()

    if not result.competitors:
        print("No competitors selected. Try: bigger --radius, --no-website-filter, "
              "or check the Places type strings in CATEGORY_TYPE_MAP.")
        return

    for rank, c in enumerate(result.competitors, 1):
        tier = "local" if c.is_local else "BENCHMARK"
        scr = "scrapable" if c.has_scrapable_site else "social-only"
        print(f"#{rank}  {c.candidate.name}   ({c.candidate.rating}\u2605 / "
              f"{c.candidate.review_count} reviews)  [{tier} / {scr}]")
        print(f"     {c.candidate.website}")
        print(f"     why: {c.selection.why_selected}")
        if c.reviews:
            print(f"     reviews fetched: {len(c.reviews)}")
            sample = c.reviews[0]
            snippet = (sample.text or "")[:120].replace("\n", " ")
            print(f"       e.g. [{sample.rating}\u2605] {snippet}{'...' if len(sample.text or '') > 120 else ''}")
        print()

    total_reviews = sum(len(c.reviews) for c in result.competitors)
    print(f"Total competitor reviews available for theming: {total_reviews}")


if __name__ == "__main__":
    main()