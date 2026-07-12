"""Apify Facebook provider — WRAPS the team's collector output (Tier-2, owner §10 sign-off;
$20/month cap on record 2026-07-12). Governance: network pulls live ONLY in scripts/
(scripts/pull_facebook.py drives facebook_collector unmodified and snapshots raw payloads
OUTSIDE the repo); this provider only PARSES. Author names are hashed AT INGESTION (PD-6 —
the fixture-conversion path hashes again by construction since it serializes SocialSignal);
raw names / profile URLs / avatar URLs never leave the snapshot."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..schemas import SocialSignal, hash_author

_AR_RE = re.compile(r"[؀-ۿ]")


def _lang_of(text: str) -> str:
    """Honest script cue only: Arabic script -> 'ar', otherwise unknown ('')."""
    return "ar" if _AR_RE.search(text or "") else ""


def _dt(value: Any) -> Optional[datetime]:
    """ISO timestamps from the actors ('...Z' included); anything else -> None (honest)."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def brand_ref_of(snapshot: dict) -> str:
    """A stable slug for the pulled page: profile.username, else the input URL's path."""
    prof = snapshot.get("profile") or {}
    if prof.get("username"):
        return str(prof["username"]).strip().strip("/").lower()
    url = str((snapshot.get("source") or {}).get("input_url") or "")
    path = url.split("facebook.com/", 1)[-1] if "facebook.com/" in url else url
    return path.strip("/").split("/")[0].split("?")[0].lower()


def signals_from_snapshot(snapshot: dict, *, is_own_brand: bool = True,
                          scraped_at: Optional[datetime] = None) -> list[SocialSignal]:
    """The team snapshot shape (facebook_collector/main.py output) -> strict SocialSignals.
    Posts are authored by the page itself; comment authors are hashed here and their raw
    name/url/picture (and the actors' `raw` payloads) are DROPPED. Malformed rows skip."""
    brand = brand_ref_of(snapshot)
    page_name = str((snapshot.get("profile") or {}).get("name") or brand)
    when = scraped_at or _dt((snapshot.get("source") or {}).get("collected_at")) \
        or datetime.now(timezone.utc)
    out: list[SocialSignal] = []
    for post in (snapshot.get("posts") or []):
        try:
            text = str(post.get("text") or "").strip()
            url = str(post.get("url") or "")
            if text:
                out.append(SocialSignal(
                    source="facebook_apify", source_url=url or f"facebook://{brand}",
                    signal_kind="post", author_hash=hash_author(page_name),
                    text=text, lang=_lang_of(text), posted_at=_dt(post.get("created_at")),
                    like_count=max(0, int(post.get("reactions_count") or 0)),
                    brand_ref=brand, is_own_brand=is_own_brand, scraped_at=when))
            for c in (post.get("comments") or []):
                ctext = str(c.get("text") or "").strip()
                if not ctext:
                    continue
                raw_name = str(((c.get("author") or {}).get("name")) or "anonymous")
                out.append(SocialSignal(
                    source="facebook_apify",
                    source_url=str(c.get("post_url") or url or f"facebook://{brand}"),
                    signal_kind="comment", author_hash=hash_author(raw_name),
                    text=ctext, lang=_lang_of(ctext), posted_at=_dt(c.get("created_at")),
                    like_count=max(0, int(c.get("likes_count") or 0)),
                    brand_ref=brand, is_own_brand=is_own_brand, scraped_at=when))
        except Exception:  # noqa: BLE001 — one malformed post never kills the batch
            continue
    return out


class ApifyFacebookProvider:
    """SocialProvider over saved snapshots/fixtures — no network, ever.
    `<dir>/<brand_ref>.json` is either a SANITIZED signal list (committed fixture) or a
    RAW team snapshot (local only, gitignored) — raw is hashed at ingestion right here."""

    source = "facebook_apify"

    def __init__(self, snapshots_dir: Optional[str] = None):
        default = Path(__file__).resolve().parent.parent / "fixtures"
        self.dir = Path(snapshots_dir) if snapshots_dir else default

    def fetch(self, brand_ref: str, *, limit: int = 200) -> list[SocialSignal]:
        path = self.dir / f"{brand_ref}.json"
        if not path.is_file():
            return []   # empty is VALID (advisor flag)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        if isinstance(data, dict) and "posts" in data:          # raw team snapshot
            return signals_from_snapshot(data)[:limit]
        if isinstance(data, list):                              # sanitized fixture
            out: list[SocialSignal] = []
            for row in data[:limit]:
                try:
                    out.append(SocialSignal(**row))
                except Exception:  # noqa: BLE001
                    continue
            return out
        return []
