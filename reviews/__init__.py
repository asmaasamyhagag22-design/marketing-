"""U8a — Review acquisition layer (v2.2, fixtures-first per PD-3/PD-4).

Schemas + a provider protocol + the FIXTURE provider (hermetic). Real network
providers (Google Maps / Vezeeta) live behind scripts/ pulls (PD-4: scripts are
the only network paths) and land as separate, measured steps.
"""
from .schemas import Review
from .providers.base import ReviewProvider
from .providers.fixture import FixtureReviewProvider

__all__ = ["Review", "ReviewProvider", "FixtureReviewProvider"]
