"""Raw Google Maps review snapshot -> committable SANITIZED fixture (PD-6).

Parses the pull-script snapshot through reviews.providers.google_maps (authors hashed,
relative dates honestly dropped) and REFUSES to write if any raw author name survives in
the serialized output — the PII gate is loud, not silent.

Usage:
    python -m scripts.convert_reviews_snapshot runs/review_snapshots/<brand>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Sanitize a raw review snapshot into a fixture.")
    ap.add_argument("snapshot", help="raw snapshot JSON (scripts/pull_reviews.py output)")
    ap.add_argument("--out-dir", default="reviews/fixtures")
    args = ap.parse_args()

    from reviews.providers.google_maps import reviews_from_snapshot
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    reviews = reviews_from_snapshot(snapshot)
    if not reviews:
        print("no reviews parsed — nothing written (empty is valid, but check the snapshot)")
        return 1

    serialized = json.dumps([r.model_dump(mode="json") for r in reviews],
                            ensure_ascii=False, indent=2)

    leaks = []
    for r in (snapshot.get("reviews") or []):
        name = str(r.get("author") or "").strip()
        if name and name in serialized:
            leaks.append(name[:60])
    if leaks:
        print("PII LEAK — fixture NOT written:")
        for x in leaks:
            print("  -", x)
        return 2

    brand = str(snapshot.get("brand_ref") or "unknown")
    out = Path(args.out_dir) / f"{brand}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(serialized, encoding="utf-8")
    print(f"wrote {len(reviews)} sanitized reviews -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
