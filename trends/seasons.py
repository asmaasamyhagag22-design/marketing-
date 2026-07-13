"""Egyptian marketing-season calendar (Round-2 A / T-SEASON).

The trend engine is date-agnostic; the census flagged that no season logic exists at all. This
is the ONE place the mission allows new computation (data genuinely absent). It is a static,
deterministic calendar of Egypt's real marketing seasons — no fabrication, and the Islamic
(Hijri) dates are flagged `approximate` because they shift ~11 days/year, so the deliverable
never presents a shifting date as exact.

Universal by construction: a plain date table, no vertical logic. `today` is passed in
(deterministic + workflow-safe); callers stamp the real date.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

# (key, arabic, english, start ISO, end ISO, approximate?) — a rolling 2026-2027 window.
_SEASONS: list[tuple[str, str, str, str, str, bool]] = [
    ("ramadan_2026", "رمضان", "Ramadan", "2026-02-18", "2026-03-19", True),
    ("eid_fitr_2026", "عيد الفطر", "Eid al-Fitr", "2026-03-20", "2026-03-23", True),
    ("mothers_day", "عيد الأم", "Mother's Day (Egypt)", "2026-03-21", "2026-03-21", False),
    ("eid_adha_2026", "عيد الأضحى", "Eid al-Adha", "2026-05-27", "2026-05-30", True),
    ("summer", "موسم الصيف والسواحل", "Summer & coast season", "2026-06-15", "2026-08-31", False),
    ("back_to_school", "العودة للمدارس", "Back to school", "2026-09-01", "2026-10-10", False),
    ("white_friday", "الجمعة البيضاء", "White (Black) Friday", "2026-11-20", "2026-11-30", False),
    ("year_end", "عروض آخر السنة", "Year-end sales", "2026-12-15", "2026-12-31", False),
    ("ramadan_2027", "رمضان", "Ramadan", "2027-02-08", "2027-03-09", True),
    ("eid_fitr_2027", "عيد الفطر", "Eid al-Fitr", "2027-03-10", "2027-03-13", True),
]


def _d(s: str) -> date:
    return date.fromisoformat(s)


def season_for_date(day: "date | str") -> Optional[dict]:
    """The season a given date falls INSIDE (for per-calendar-item attribution). None if none."""
    try:
        d = day if isinstance(day, date) else _d(str(day)[:10])
    except Exception:  # noqa: BLE001
        return None
    for key, ar, en, s, e, approx in _SEASONS:
        if _d(s) <= d <= _d(e):
            return {"key": key, "ar": ar, "en": en, "start": s, "end": e, "approximate": approx}
    return None


def upcoming_season(today: "date | str", *, within_days: int = 120) -> Optional[dict]:
    """The nearest season STARTING within `within_days` of `today` (the Market-Pulse window).
    Returns the season dict + `days_until`, or None when nothing is close."""
    try:
        t = today if isinstance(today, date) else _d(str(today)[:10])
    except Exception:  # noqa: BLE001
        return None
    best = None
    for key, ar, en, s, e, approx in _SEASONS:
        start = _d(s)
        if _d(e) < t:                      # already over
            continue
        days_until = (start - t).days
        if days_until <= within_days:      # currently in it (<=0) or starting soon
            cand = {"key": key, "ar": ar, "en": en, "start": s, "end": e,
                    "approximate": approx, "days_until": max(0, days_until),
                    "active": start <= t <= _d(e)}
            if best is None or days_until < best["days_until"] and not best["active"]:
                best = cand
            if cand["active"]:             # an active season wins outright
                return cand
    return best
