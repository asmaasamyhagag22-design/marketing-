"""U1 config — KPI targets + channel weights BY CATEGORY, always with a universal default
(INTERFACES §F: "config.py (KPI + channel weights CONFIG by category + default)"; D-8: config
keyed by the profile's universal category signal, never vertical logic in code).

Numbers here are STARTING POINTS for the advisor (industry-typical planning priors), not
promises — every one is overridable and the dashboard surfaces them as editable. The KPI
metric names align with `schemas._COST_PER_RESULT_METRICS` so the 3×CPL learning floor
(`CampaignObjective._learning_floor`) engages automatically when a target is set.
"""
from __future__ import annotations

from typing import Optional

from .schemas import KPITarget, MetaObjective

# ---------------------------------------------------------------------
# Channel weights: relative budget emphasis per channel, by category class.
# Universal default first; categories only OVERRIDE what differs.
# ---------------------------------------------------------------------

_DEFAULT_CHANNELS: dict[str, float] = {
    "facebook": 0.40, "instagram": 0.40, "tiktok": 0.10, "youtube": 0.10,
}

_CHANNELS_BY_CATEGORY: dict[str, dict[str, float]] = {
    # visual product verticals lean harder into IG/TikTok
    "ecommerce": {"facebook": 0.30, "instagram": 0.40, "tiktok": 0.20, "youtube": 0.10},
    "retail":    {"facebook": 0.30, "instagram": 0.40, "tiktok": 0.20, "youtube": 0.10},
    "beauty":    {"facebook": 0.25, "instagram": 0.45, "tiktok": 0.20, "youtube": 0.10},
    "restaurant": {"facebook": 0.35, "instagram": 0.40, "tiktok": 0.20, "youtube": 0.05},
    "cafe":      {"facebook": 0.35, "instagram": 0.40, "tiktok": 0.20, "youtube": 0.05},
    # trust/consideration verticals lean FB/YT
    "clinic":    {"facebook": 0.50, "instagram": 0.30, "tiktok": 0.05, "youtube": 0.15},
    "hospital":  {"facebook": 0.50, "instagram": 0.30, "tiktok": 0.05, "youtube": 0.15},
    "education": {"facebook": 0.45, "instagram": 0.25, "tiktok": 0.10, "youtube": 0.20},
    "government": {"facebook": 0.55, "instagram": 0.25, "tiktok": 0.05, "youtube": 0.15},
    "services_b2b": {"facebook": 0.45, "instagram": 0.20, "tiktok": 0.05, "youtube": 0.30},
}


def channel_weights(category: Optional[str]) -> dict[str, float]:
    """Channel emphasis for a category (universal default when unknown). Always sums to 1.0."""
    w = dict(_CHANNELS_BY_CATEGORY.get((category or "").strip().lower(), _DEFAULT_CHANNELS))
    total = sum(w.values()) or 1.0
    return {k: round(v / total, 4) for k, v in w.items()}


# ---------------------------------------------------------------------
# KPI planning priors: metric + typical window per objective, tuned per category class.
# target_value stays None unless the category prior sets one — an HONEST unknown engages
# no learning-floor math (the schema only enforces 3×CPL when a target exists).
# ---------------------------------------------------------------------

_KPI_METRIC_BY_OBJECTIVE: dict[MetaObjective, str] = {
    MetaObjective.SALES: "cost_per_purchase",
    MetaObjective.LEADS: "cost_per_lead",
    MetaObjective.TRAFFIC: "cost_per_click",
    MetaObjective.ENGAGEMENT: "cost_per_engagement",
    MetaObjective.AWARENESS: "cpm",
    MetaObjective.APP_PROMOTION: "cost_per_install",
}


def default_kpi(objective: MetaObjective, category: Optional[str] = None) -> KPITarget:
    """The planning KPI for an objective (metric + 7-day window; no invented target_value)."""
    return KPITarget(metric=_KPI_METRIC_BY_OBJECTIVE.get(objective, "cost_per_result"),
                     target_value=None, unit="EGP", window_days=7)
