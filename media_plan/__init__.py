"""U1 — Media Plan.

Deduces the ONE Meta campaign objective (+ destination + KPI) a brand should run, grounded in
its real evidence and Ledger-verified. This package is additive and does not touch the existing
profile/render pipeline (INTERFACES.md §F). Schemas are strict (PD-5); the builder runs on the
shared Caller + MockCaller (PD-4 fixtures-first, offline-testable).
"""
from .schemas import (
    CampaignObjective,
    Destination,
    EvidenceRef,
    KPITarget,
    MetaObjective,
)

__all__ = [
    "MetaObjective",
    "Destination",
    "KPITarget",
    "EvidenceRef",
    "CampaignObjective",
]
