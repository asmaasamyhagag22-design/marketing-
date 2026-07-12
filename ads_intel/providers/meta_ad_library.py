"""Meta Ad Library provider — parse-only (PD-4: the network pull lives in
scripts/pull_meta_ads.py behind the owner's META_ADS_TOKEN; the official Graph API
`ads_archive` endpoint is free but token-gated). This provider parses SAVED snapshots
(runs/ad_snapshots/<ref>.json, gitignored) or committed sanitized fixtures."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..schemas import CompetitorAd


def _d(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except Exception:  # noqa: BLE001
        return None


def ads_from_snapshot(snapshot: dict) -> list[CompetitorAd]:
    """The pull-script snapshot shape (Graph API ads_archive rows) -> strict ads.
    Malformed rows skip; unknown creative format stays an honest ''."""
    ref = str(snapshot.get("brand_ref") or "")
    when = datetime.now(timezone.utc)
    try:
        when = datetime.fromisoformat(str(snapshot.get("pulled_at")).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        pass
    out: list[CompetitorAd] = []
    for r in (snapshot.get("ads") or []):
        try:
            body = ""
            bodies = r.get("ad_creative_bodies") or []
            if bodies:
                body = str(bodies[0] or "")[:500]
            fmt = str(r.get("media_type") or "").lower()
            out.append(CompetitorAd(
                source="meta_ad_library",
                ad_id=str(r.get("id") or ""),
                page_name=str(r.get("page_name") or ""),
                brand_ref=ref,
                platforms=[str(p).lower() for p in (r.get("publisher_platforms") or [])],
                started_at=_d(r.get("ad_delivery_start_time")),
                is_active=not r.get("ad_delivery_stop_time"),
                creative_format={"video": "video", "image": "image"}.get(fmt, fmt),
                ad_text=body,
                snapshot_url=str(r.get("ad_snapshot_url") or ""),
                scraped_at=when,
            ))
        except Exception:  # noqa: BLE001
            continue
    return out


class MetaAdLibraryProvider:
    source = "meta_ad_library"

    def __init__(self, snapshots_dir: Optional[str] = None):
        default = Path(__file__).resolve().parent.parent / "fixtures"
        self.dir = Path(snapshots_dir) if snapshots_dir else default

    def fetch(self, brand_ref: str, *, limit: int = 50) -> list[CompetitorAd]:
        path = self.dir / f"{brand_ref}.json"
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        if isinstance(data, dict) and "ads" in data:            # raw pull snapshot
            return ads_from_snapshot(data)[:limit]
        if isinstance(data, list):                              # sanitized fixture rows
            out: list[CompetitorAd] = []
            for row in data[:limit]:
                try:
                    out.append(CompetitorAd(**row))
                except Exception:  # noqa: BLE001
                    continue
            return out
        return []
