"""U1 — Media Plan.

Deduces the Meta campaign objective(s) a brand should run — grounded in its real evidence,
Ledger-verified, with a funnel-ordered budget split. Additive; does not touch the existing
profile/render pipeline (INTERFACES.md §F). Schemas are strict (PD-5); the builder runs on the
shared Caller + MockCaller (PD-4 fixtures-first, offline-testable).
"""
from .builder import build_campaign_objective, conversion_signals
from .schemas import (
    CampaignObjective,
    Destination,
    EvidenceRef,
    FunnelStage,
    GeoMode,
    GeoTargeting,
    KPITarget,
    MediaPlan,
    MetaObjective,
    Persona,
)

__all__ = [
    "build_campaign_objective",
    "conversion_signals",
    "MetaObjective",
    "FunnelStage",
    "Destination",
    "GeoMode",
    "KPITarget",
    "EvidenceRef",
    "Persona",
    "GeoTargeting",
    "CampaignObjective",
    "MediaPlan",
]
