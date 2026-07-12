"""ONE-SHOT Instagram pull via the OFFICIAL Graph API (PD-4: the only network path).
This is U9's Tier-1 Instagram source — the direct scraper was Tier-4 REJECTED; Business
Discovery + own-media are the sanctioned doors. Raw snapshots (comment author usernames =
PII) land under runs/social_snapshots/ (gitignored); providers hash at ingestion.

Modes:
  --own                 the owner's linked IG business account: media + comments
                        (customer voice -> ABSA own-brand rows)
  --peer <username>     a competitor business account via business_discovery:
                        public media, captions, engagement counts (no comments text —
                        the API does not expose other accounts' comments)

Usage:
    python -m scripts.pull_instagram --own --brand-ref mybrand
    python -m scripts.pull_instagram --peer eldahan_grill --brand-ref eldahan
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


def _g(path: str, token: str, **params):
    params["access_token"] = token
    url = f"https://graph.facebook.com/v21.0/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _own_ig_id(token: str) -> str | None:
    accts = _g("me/accounts", token, fields="id,name,instagram_business_account")
    for p in accts.get("data") or []:
        ig = p.get("instagram_business_account")
        if ig:
            return ig["id"]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Official Instagram pull (Business Discovery).")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--own", action="store_true")
    grp.add_argument("--peer", default=None, help="competitor IG business username")
    ap.add_argument("--brand-ref", required=True)
    ap.add_argument("--limit", type=int, default=15, help="media items")
    ap.add_argument("--comments", type=int, default=25, help="comments per media (--own only)")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(".env")
    token = os.environ.get("IG_ACCESS_TOKEN")
    if not token:
        print("IG_ACCESS_TOKEN missing from .env")
        return 2
    ig_id = _own_ig_id(token)
    if not ig_id:
        print("no linked Instagram business account on this token's pages")
        return 2

    if args.own:
        media = _g(f"{ig_id}/media", token, limit=args.limit,
                   fields="id,caption,media_type,permalink,timestamp,like_count,comments_count")
        items = media.get("data") or []
        for m in items:
            try:
                c = _g(f"{m['id']}/comments", token, limit=args.comments,
                       fields="id,text,username,timestamp,like_count")
                m["comments"] = c.get("data") or []
            except Exception:  # noqa: BLE001 — comments may be off per media
                m["comments"] = []
        snapshot = {"source": "ig_business", "mode": "own", "brand_ref": args.brand_ref,
                    "is_own_brand": True, "ig_user_id": ig_id,
                    "pulled_at": datetime.now(timezone.utc).isoformat(), "media": items}
        n_comments = sum(len(m.get("comments") or []) for m in items)
        summary = f"{len(items)} media, {n_comments} comments"
    else:
        fields = (f"business_discovery.username({args.peer})"
                  f"{{username,followers_count,media_count,"
                  f"media.limit({args.limit}){{caption,media_type,permalink,timestamp,"
                  f"like_count,comments_count}}}}")
        bd = _g(ig_id, token, fields=fields)["business_discovery"]
        snapshot = {"source": "ig_business", "mode": "peer", "brand_ref": args.brand_ref,
                    "is_own_brand": False, "peer_username": args.peer,
                    "followers_count": bd.get("followers_count"),
                    "media_count": bd.get("media_count"),
                    "pulled_at": datetime.now(timezone.utc).isoformat(),
                    "media": (bd.get("media") or {}).get("data") or []}
        summary = f"@{args.peer}: {len(snapshot['media'])} media, {bd.get('followers_count')} followers"

    out = Path("runs") / "social_snapshots" / f"{args.brand_ref}_ig.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{summary} -> {out}")
    print("(RAW snapshot — comment usernames are PII; stays out of git. Convert via "
          "social_intel.providers.ig_business at ingestion.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
