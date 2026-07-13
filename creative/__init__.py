"""Creative-variety engine (owner directive 2026-07-13): lock WITHIN a run, vary ACROSS
runs. The sampler draws a (narrative archetype, motif domain, protagonist slot) triple —
filtered by the brand's real audience — so every run gets a deliberately different creative
direction instead of leaving variety to chance. The Director receives the triple as strong
defaults (§1) and an AVOID list of the client's recent runs (history ledger)."""
from .sampler import (
    CreativeDirection,
    load_library,
    sample_direction,
    sample_distinct_directions,
)

__all__ = [
    "CreativeDirection",
    "load_library",
    "sample_direction",
    "sample_distinct_directions",
]
