"""Raw Facebook snapshot -> committable SANITIZED fixture (PD-6: hash at fixture-conversion).

Parses the team-collector snapshot through social_intel.providers.apify_facebook (authors
hashed, raw payloads dropped) and REFUSES to write if any raw author name or profile URL
from the snapshot survives in the serialized output — the PII gate is loud, not silent.

Usage:
    python -m scripts.convert_facebook_snapshot facebook_collector/facebook_output.json
    python -m scripts.convert_facebook_snapshot <snapshot.json> --peer   # competitor page
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Sanitize a raw Facebook snapshot into a fixture.")
    ap.add_argument("snapshot", help="raw snapshot JSON (team collector output shape)")
    ap.add_argument("--peer", action="store_true",
                    help="competitor page (signals feed O/T, not S/W)")
    ap.add_argument("--out-dir", default="social_intel/fixtures")
    args = ap.parse_args()

    from social_intel.providers.apify_facebook import brand_ref_of, signals_from_snapshot
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    signals = signals_from_snapshot(snapshot, is_own_brand=not args.peer)
    if not signals:
        print("no signals parsed — nothing written (empty is valid, but check the snapshot)")
        return 1

    serialized = json.dumps([s.model_dump(mode="json") for s in signals],
                            ensure_ascii=False, indent=2)

    # PII gate: no raw author name / profile URL / avatar URL may survive sanitization
    leaks: list[str] = []
    for post in (snapshot.get("posts") or []):
        for c in (post.get("comments") or []):
            a = c.get("author") or {}
            for label in ("name", "url", "picture"):
                v = str(a.get(label) or "").strip()
                if v and v in serialized:
                    leaks.append(f"{label}: {v[:60]}")
    if leaks:
        print("PII LEAK — fixture NOT written:")
        for x in leaks:
            print("  -", x)
        return 2

    brand = brand_ref_of(snapshot)
    out = Path(args.out_dir) / f"{brand}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(serialized, encoding="utf-8")
    print(f"wrote {len(signals)} sanitized signals -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
