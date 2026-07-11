"""U8a schemas (strict, PD-5). Privacy rule from the v2.2 plan: `author_hash` NEVER a raw
name — the SHA-256 fingerprint (telemetry.payload_hash — hashing lives there, D-3)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["google_maps", "vezeeta", "fixture"]
    source_url: str
    author_hash: str = Field(min_length=8)          # NEVER a raw name
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    text: str
    review_date: Optional[date] = None
    lang: str = ""
    scraped_at: datetime


def hash_author(raw_name: str) -> str:
    """The one blessed way to fingerprint an author (raw names never leave the provider)."""
    from telemetry import payload_hash
    return payload_hash((raw_name or "").strip().lower())[:16]
