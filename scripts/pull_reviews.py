"""ONE-SHOT Google Maps review pull (PD-4: network pulls live ONLY here, never in providers).

Resolves a place (by --place-id or a text query) through the existing competitor
PlacesClient, pulls its reviews (Google's hard cap: ~5 per place), and SNAPSHOTS the raw
payload (carries author names — PII) under runs/review_snapshots/ (gitignored). Convert to
a committable fixture with scripts/convert_reviews_snapshot.py. NO recurring scheduling.

Usage:
    python -m scripts.pull_reviews "Alameda Healthcare Cairo" --brand-ref alameda --own
    python -m scripts.pull_reviews --place-id ChIJ... --brand-ref peer_clinic --peer
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Capped one-shot Google Maps review pull.")
    ap.add_argument("query", nargs="?", default=None,
                    help="place text query (name + city); or use --place-id")
    ap.add_argument("--place-id", default=None)
    ap.add_argument("--brand-ref", required=True, help="stable slug for this brand")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--own", action="store_true", help="the subject brand (default)")
    grp.add_argument("--peer", action="store_true", help="a competitor")
    args = ap.parse_args()
    if not (args.query or args.place_id):
        ap.error("give a text query or --place-id")

    from competitor.places_client import PlacesClient
    client = PlacesClient()

    place_id = args.place_id
    resolved_name = None
    if not place_id:
        hits = client.search_text(args.query, max_results=1)
        if not hits:
            print(f"no place found for query: {args.query!r}")
            return 1
        place_id, resolved_name = hits[0].place_id, hits[0].name
        print(f"resolved: {resolved_name!r} -> {place_id}")

    reviews = client.get_reviews(place_id)
    snapshot = {
        "source": "google_maps",
        "brand_ref": args.brand_ref,
        "is_own_brand": not args.peer,
        "place_id": place_id,
        "query": args.query,
        "resolved_name": resolved_name,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "reviews": [asdict(r) for r in reviews],
    }
    out = Path("runs") / "review_snapshots" / f"{args.brand_ref}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(reviews)} reviews (Google caps at ~5/place)")
    print(f"snapshot (RAW, PII — stays out of git): {out}")
    print("next: python -m scripts.convert_reviews_snapshot", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
