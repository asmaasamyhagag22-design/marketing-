"""FIXTURE provider — the hermetic backbone (PD-3): reads ads_intel/fixtures/<ref>.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..schemas import CompetitorAd

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class FixtureAdsProvider:
    source = "fixture"

    def __init__(self, fixtures_dir: Optional[str] = None):
        self.dir = Path(fixtures_dir) if fixtures_dir else _FIXTURES_DIR

    def fetch(self, brand_ref: str, *, limit: int = 50) -> list[CompetitorAd]:
        path = self.dir / f"{brand_ref}.json"
        if not path.is_file():
            return []
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        out: list[CompetitorAd] = []
        for r in rows[:limit]:
            try:
                r.setdefault("source", "fixture")
                r.setdefault("brand_ref", brand_ref)
                r.setdefault("scraped_at", datetime.now(timezone.utc).isoformat())
                out.append(CompetitorAd(**r))
            except Exception:  # noqa: BLE001 — one malformed row never kills the batch
                continue
        return out
