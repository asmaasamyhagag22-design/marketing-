"""SocialSignal — strict (PD-5), privacy-hashed at ingestion (PD-6, same rule as U8a)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class SocialSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["facebook_apify", "ig_business_discovery", "youtube_api",
                    "snapshot", "fixture"]
    source_url: str
    signal_kind: Literal["comment", "post", "reply", "caption"]
    author_hash: str = Field(min_length=8)          # NEVER a raw name (PD-6)
    text: str
    lang: str = ""
    posted_at: Optional[datetime] = None
    like_count: Optional[int] = Field(default=None, ge=0)
    brand_ref: str = ""                              # whose page/post this came from
    is_own_brand: bool = False                       # own-brand -> S/W; peer -> O/T (R-5)
    scraped_at: datetime


def hash_author(raw_name: str) -> str:
    from telemetry import payload_hash
    return payload_hash((raw_name or "").strip().lower())[:16]
