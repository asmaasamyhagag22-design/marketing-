"""Content strategy + calendar builder.

    from strategy import build_strategy
    calendar = build_strategy(profile, caller, days=30)
    calendar.save("plan.json")
"""
from .builder import build_strategy, ContentCalendar, ContentItem

__all__ = ["build_strategy", "ContentCalendar", "ContentItem"]
