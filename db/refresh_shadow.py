"""Bind an advisory refresh comparison to the exact historical strategy and captures."""
import logging

from strategy.positioning.refresh_shadow import (
    POLICY, compare_captures, current_profile_excerpt, strategy_dependencies,
)

logger = logging.getLogger(__name__)


def observe_refresh(uow, *, brand, profile, capture):
    strategy = None
    try:
        with uow.session.begin_nested():
            strategy = uow.runs.current_successful(brand_id=brand.id, kind="strategy")
            if strategy is None:
                return None
            canonical = (strategy.output or {}).get("canonical_strategy")
            approval = uow.approvals.latest_for_run(strategy.id)
            if not canonical or approval is None or approval.decision != "approved":
                return None
            if strategy.input_profile_id == profile.id:
                return None
            old_scrape = uow.runs.scrape_for_profile(
                brand_id=brand.id, profile_id=strategy.input_profile_id)
            before = (old_scrape.output or {}).get("source_capture") if old_scrape else None
            result = compare_captures(before, capture, strategy_dependencies(canonical))
            if result["changes"] and strategy.input_profile_id is not None:
                old_profile = uow.profiles.by_id(strategy.input_profile_id)
                if old_profile is not None and old_profile.brand_id == brand.id:
                    for change in result["changes"]:
                        for dependency in change["impacts"]:
                            dependency["current_excerpt"] = current_profile_excerpt(
                                old_profile.profile, profile.profile, dependency)
    except Exception:
        logger.warning("Advisory source comparison unavailable during scrape")
        if strategy is None:
            return None
        result = {"policy": POLICY, "mode": "shadow", "decision": "UNKNOWN",
                  "reasons": ["SHADOW_COMPARISON_UNAVAILABLE"], "changes": []}
    return {**result, "strategy_run_id": str(strategy.id),
            "from_profile_snapshot_id": str(strategy.input_profile_id or ""),
            "to_profile_snapshot_id": str(profile.id)}
