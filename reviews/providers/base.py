"""The provider protocol — one universal interface per source (a provider-per-source IS
universal, D-8). Implementations must be deterministic given their inputs; network pulls
happen in scripts/ (PD-4) which SNAPSHOT raw payloads the providers then parse."""
from __future__ import annotations

from typing import Protocol

from ..schemas import Review


class ReviewProvider(Protocol):
    source: str

    def fetch(self, brand_ref: str, *, limit: int = 100) -> list[Review]:
        """Reviews for a brand reference (place id / provider-specific key). Empty list is
        a VALID result (advisor flags thin data); raising is reserved for malformed input."""
        ...
