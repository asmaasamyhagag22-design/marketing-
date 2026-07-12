"""ONE-SHOT Meta Ad Library pull (PD-4: network pulls live ONLY here). Official Graph API,
free, but requires the owner's META_ADS_TOKEN (a Meta app access token with Ad Library API
access — https://www.facebook.com/ads/library/api). Snapshots land under runs/ad_snapshots/
(gitignored); convert/commit a sanitized fixture only if needed for tests.

Usage:
    python -m scripts.pull_meta_ads "El Dahan Grill" --brand-ref eldahan --country EG
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_FIELDS = ("id,page_name,ad_delivery_start_time,ad_delivery_stop_time,"
           "publisher_platforms,ad_creative_bodies,ad_snapshot_url,media_type")


def main() -> int:
    ap = argparse.ArgumentParser(description="One-shot Meta Ad Library pull (official API).")
    ap.add_argument("query", help="competitor page name to search")
    ap.add_argument("--brand-ref", required=True)
    ap.add_argument("--country", default="EG")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    token = os.environ.get("META_ADS_TOKEN")
    if not token:
        print("META_ADS_TOKEN is not set — the owner must create a Meta app token with "
              "Ad Library API access (free): https://www.facebook.com/ads/library/api")
        return 2

    params = urllib.parse.urlencode({
        "search_terms": args.query,
        "ad_reached_countries": f'["{args.country}"]',
        "ad_active_status": "ACTIVE",
        "fields": _FIELDS,
        "limit": min(args.limit, 100),
        "access_token": token,
    })
    url = f"https://graph.facebook.com/v21.0/ads_archive?{params}"
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))

    snapshot = {
        "source": "meta_ad_library",
        "brand_ref": args.brand_ref,
        "query": args.query,
        "country": args.country,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "ads": data.get("data") or [],
    }
    out = Path("runs") / "ad_snapshots" / f"{args.brand_ref}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(snapshot['ads'])} active ad(s) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
