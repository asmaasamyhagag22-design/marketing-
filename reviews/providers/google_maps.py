"""Google Maps review provider — parse-only (PD-4: the network pull lives in
scripts/pull_reviews.py, which SNAPSHOTS the raw Places payload OUTSIDE the repo).
Author names are hashed AT INGESTION (PD-6); raw names never leave the snapshot.

Honest limits carried from the Places API: at most ~5 reviews per place (Google's hard
cap — themes stay DIRECTIONAL) and only a RELATIVE publish time ("a month ago"), so
review_date is an honest None rather than a fabricated date."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..schemas import Review, hash_author

_AR_RE = re.compile(r"[؀-ۿ]")


def _lang_of(text: str, code: Optional[str]) -> str:
    if code:
        return str(code).split("-")[0].lower()
    return "ar" if _AR_RE.search(text or "") else ""


def _dt(value) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)


def reviews_from_snapshot(snapshot: dict) -> list[Review]:
    """The pull-script snapshot shape -> strict Reviews. Malformed rows skip."""
    place_id = str(snapshot.get("place_id") or "")
    src_url = (f"https://www.google.com/maps/place/?q=place_id:{place_id}"
               if place_id else f"google_maps://{snapshot.get('brand_ref') or 'unknown'}")
    when = _dt(snapshot.get("pulled_at"))
    out: list[Review] = []
    for r in (snapshot.get("reviews") or []):
        try:
            text = str(r.get("text") or "").strip()
            if not text:
                continue
            out.append(Review(
                source="google_maps",
                source_url=src_url,
                author_hash=hash_author(str(r.get("author") or "anonymous")),
                rating=r.get("rating"),
                text=text,
                review_date=None,   # Places gives only relative time — never invent a date
                lang=_lang_of(text, r.get("language_code")),
                scraped_at=when,
            ))
        except Exception:  # noqa: BLE001 — one malformed row never kills the batch
            continue
    return out


class GoogleMapsReviewProvider:
    """ReviewProvider over saved snapshots/fixtures — no network, ever.
    `<dir>/<brand_ref>.json` is either a RAW pull snapshot (local only, carries author
    names — hashed right here) or a SANITIZED fixture (list of Review dicts)."""

    source = "google_maps"

    def __init__(self, snapshots_dir: Optional[str] = None):
        default = Path(__file__).resolve().parent.parent / "fixtures"
        self.dir = Path(snapshots_dir) if snapshots_dir else default

    def fetch(self, brand_ref: str, *, limit: int = 100) -> list[Review]:
        path = self.dir / f"{brand_ref}.json"
        if not path.is_file():
            return []                                   # empty is VALID -> advisor flag
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        if isinstance(data, dict) and "reviews" in data:        # raw pull snapshot
            return reviews_from_snapshot(data)[:limit]
        if isinstance(data, list):                              # sanitized fixture
            out: list[Review] = []
            for row in data[:limit]:
                try:
                    out.append(Review(**row))
                except Exception:  # noqa: BLE001
                    continue
            return out
        return []
