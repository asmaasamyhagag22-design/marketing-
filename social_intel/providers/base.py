"""Provider Protocol — one per source (a provider-per-source is universal, D-8).
Network pulls live in scripts/ (PD-4) and SNAPSHOT raw payloads; providers only parse."""
from __future__ import annotations

from typing import Protocol

from ..schemas import SocialSignal


class SocialProvider(Protocol):
    source: str

    def fetch(self, brand_ref: str, *, limit: int = 200) -> list[SocialSignal]:
        """Signals for a brand reference. Empty list is VALID (advisor flag)."""
        ...
