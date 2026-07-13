# -*- coding: utf-8 -*-
"""Egyptian marketing-season calendar (T-SEASON) — hermetic, deterministic."""
from __future__ import annotations

from datetime import date

from trends.seasons import season_for_date, upcoming_season


def test_season_for_date_inside_a_window():
    s = season_for_date("2026-09-15")
    assert s and s["key"] == "back_to_school" and "العودة للمدارس" in s["ar"]
    assert season_for_date("2026-09-15")["approximate"] is False
    r = season_for_date("2026-03-01")
    assert r and r["key"] == "ramadan_2026" and r["approximate"] is True   # Hijri -> approximate
    assert season_for_date("2026-04-10") is None                           # between seasons


def test_upcoming_season_window():
    # mid-July is INSIDE the summer season -> the active season wins outright
    up = upcoming_season("2026-07-12", within_days=120)
    assert up and up["key"] == "summer" and up["active"] is True and up["days_until"] == 0
    # mid-May (between eid_adha not yet started and after nothing) -> eid al-Adha upcoming
    nxt = upcoming_season("2026-05-01", within_days=120)
    assert nxt and nxt["key"] == "eid_adha_2026" and nxt["active"] is False
    assert nxt["days_until"] == (date(2026, 5, 27) - date(2026, 5, 1)).days
    # inside Ramadan -> the active season wins outright
    active = upcoming_season("2026-03-01")
    assert active and active["key"] == "ramadan_2026" and active["active"] is True


def test_upcoming_none_when_nothing_close():
    # early Nov: nothing active, White Friday (Nov 20) is >5 days out
    assert upcoming_season("2026-11-05", within_days=5) is None


def test_bad_input_degrades():
    assert season_for_date("not-a-date") is None
    assert upcoming_season("nonsense") is None
