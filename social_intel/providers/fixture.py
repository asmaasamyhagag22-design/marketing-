"""Fixture provider — the hermetic backbone U9 develops against (PD-3)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..schemas import SocialSignal, hash_author

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class FixtureSocialProvider:
    source = "fixture"

    def __init__(self, fixtures_dir: Optional[str] = None):
        self.dir = Path(fixtures_dir) if fixtures_dir else _FIXTURES_DIR

    def fetch(self, brand_ref: str, *, limit: int = 200) -> list[SocialSignal]:
        path = self.dir / f"{brand_ref}.json"
        if not path.is_file():
            return []
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        out: list[SocialSignal] = []
        for r in rows[:limit]:
            try:
                out.append(SocialSignal(
                    source="fixture",
                    source_url=str(r.get("source_url") or f"fixture://{brand_ref}"),
                    signal_kind=str(r.get("kind") or "comment"),
                    author_hash=hash_author(str(r.get("author") or "anonymous")),
                    text=str(r.get("text") or ""),
                    lang=str(r.get("lang") or ""),
                    like_count=r.get("likes"),
                    brand_ref=brand_ref,
                    is_own_brand=bool(r.get("is_own_brand", False)),
                    scraped_at=datetime.now(timezone.utc),
                ))
            except Exception:  # noqa: BLE001
                continue
        return out
