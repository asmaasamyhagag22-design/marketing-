"""FIXTURE provider — the hermetic backbone (fixtures-first, PD-3): reads
reviews/fixtures/<brand_key>.json, hashes authors, validates into Review models.
Every downstream unit (ABSA -> SWOT v2) develops and tests against THIS provider."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..schemas import Review, hash_author

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class FixtureReviewProvider:
    source = "fixture"

    def __init__(self, fixtures_dir: Optional[str] = None):
        self.dir = Path(fixtures_dir) if fixtures_dir else _FIXTURES_DIR

    def fetch(self, brand_ref: str, *, limit: int = 100) -> list[Review]:
        path = self.dir / f"{brand_ref}.json"
        if not path.is_file():
            return []                                   # empty is VALID -> advisor flag
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        out: list[Review] = []
        for r in rows[:limit]:
            try:
                out.append(Review(
                    source="fixture",
                    source_url=str(r.get("source_url") or f"fixture://{brand_ref}"),
                    author_hash=hash_author(str(r.get("author") or "anonymous")),
                    rating=r.get("rating"),
                    text=str(r.get("text") or ""),
                    review_date=r.get("review_date"),
                    lang=str(r.get("lang") or ""),
                    scraped_at=datetime.now(timezone.utc),
                ))
            except Exception:  # noqa: BLE001 — one malformed row never kills the batch
                continue
        return out
