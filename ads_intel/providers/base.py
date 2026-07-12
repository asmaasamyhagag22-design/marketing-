"""Provider protocol — one per source (D-8). Network pulls live in scripts/ (PD-4) and
SNAPSHOT raw payloads; providers only parse."""
from __future__ import annotations

from typing import Protocol

from ..schemas import CompetitorAd


class AdsProvider(Protocol):
    source: str

    def fetch(self, brand_ref: str, *, limit: int = 50) -> list[CompetitorAd]:
        """Running ads for a competitor reference. Empty list is VALID (a brand that runs
        no ads is itself a signal); raising is reserved for malformed input."""
        ...
