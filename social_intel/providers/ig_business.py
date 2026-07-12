"""Instagram Business Discovery provider — parse-only (PD-4; the network pull lives in
scripts/pull_instagram.py behind the owner's official IG_ACCESS_TOKEN). U9's Tier-1
Instagram door — the direct scraper was Tier-4 REJECTED.

Signals produced:
  * own-mode snapshots: the brand's media captions (posts) + customer COMMENTS —
    comment authors hashed AT INGESTION (PD-6), usernames never leave the snapshot;
  * peer-mode snapshots: the competitor's public captions as posts (their marketing
    voice — feeds competitive/content intelligence; the API exposes no peer comments)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..schemas import SocialSignal, hash_author

_AR_RE = re.compile(r"[؀-ۿ]")


def _lang(text: str) -> str:
    return "ar" if _AR_RE.search(text or "") else ""


def _dt(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except Exception:  # noqa: BLE001
        return None


def signals_from_snapshot(snapshot: dict) -> list[SocialSignal]:
    """The pull-script snapshot -> strict SocialSignals. Malformed rows skip."""
    brand = str(snapshot.get("brand_ref") or "")
    own = bool(snapshot.get("is_own_brand", snapshot.get("mode") == "own"))
    page_author = str(snapshot.get("peer_username") or snapshot.get("ig_user_id") or brand)
    when = _dt(snapshot.get("pulled_at")) or datetime.now(timezone.utc)
    out: list[SocialSignal] = []
    for m in (snapshot.get("media") or []):
        try:
            cap = str(m.get("caption") or "").strip()
            url = str(m.get("permalink") or f"instagram://{brand}")
            if cap:
                out.append(SocialSignal(
                    source="ig_business_discovery", source_url=url, signal_kind="caption",
                    author_hash=hash_author(page_author), text=cap, lang=_lang(cap),
                    posted_at=_dt(m.get("timestamp")),
                    like_count=max(0, int(m.get("like_count") or 0)),
                    brand_ref=brand, is_own_brand=own, scraped_at=when))
            for c in (m.get("comments") or []):
                txt = str(c.get("text") or "").strip()
                if not txt:
                    continue
                out.append(SocialSignal(
                    source="ig_business_discovery", source_url=url, signal_kind="comment",
                    author_hash=hash_author(str(c.get("username") or "anonymous")),
                    text=txt, lang=_lang(txt), posted_at=_dt(c.get("timestamp")),
                    like_count=max(0, int(c.get("like_count") or 0)),
                    brand_ref=brand, is_own_brand=own, scraped_at=when))
        except Exception:  # noqa: BLE001 — one malformed media never kills the batch
            continue
    return out


class IgBusinessProvider:
    """SocialProvider over saved snapshots/fixtures — no network, ever."""

    source = "ig_business_discovery"

    def __init__(self, snapshots_dir: Optional[str] = None):
        default = Path(__file__).resolve().parent.parent / "fixtures"
        self.dir = Path(snapshots_dir) if snapshots_dir else default

    def fetch(self, brand_ref: str, *, limit: int = 200) -> list[SocialSignal]:
        path = self.dir / f"{brand_ref}_ig.json"
        if not path.is_file():
            path = self.dir / f"{brand_ref}.json"
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        if isinstance(data, dict) and "media" in data:
            return signals_from_snapshot(data)[:limit]
        if isinstance(data, list):
            out: list[SocialSignal] = []
            for row in data[:limit]:
                try:
                    out.append(SocialSignal(**row))
                except Exception:  # noqa: BLE001
                    continue
            return out
        return []
