"""Strategy / content-calendar builder — hermetic (MockCaller or no caller)."""
from __future__ import annotations

import json
from pathlib import Path

from strategy import build_strategy, ContentCalendar
from strategy.builder import _PlanItem, _PlanResponse
from business_profile.llm.caller import MockCaller


def _profile():
    return {
        "name": {"value": "Glamira"},
        "category": {"value": "jewelry_ecommerce"},
        "offerings": [{"name": {"value": "Diamond Rings"}}, {"name": "Gold Necklaces"}],
    }


def test_llm_plan_is_dated_from_day_offsets():
    plan = _PlanResponse(items=[
        _PlanItem(day_offset=0, platform="instagram", content_type="reel",
                  topic="Diamond Rings", angle="luxury", hook="See this sparkle"),
        _PlanItem(day_offset=3, platform="tiktok", content_type="post",
                  topic="Gold Necklaces", angle="trend", hook="New drop"),
    ])
    mock = MockCaller({"content_strategy": plan})
    cal = build_strategy(_profile(), mock, days=30, start_date="2026-06-20")
    assert isinstance(cal, ContentCalendar)
    assert [(i.date, i.topic) for i in cal.items] == [
        ("2026-06-20", "Diamond Rings"),
        ("2026-06-23", "Gold Necklaces"),
    ]


def test_fallback_without_caller_cycles_real_offerings():
    cal = build_strategy(_profile(), None, days=14, start_date="2026-06-20", cadence_per_week=7)
    assert len(cal.items) >= 1
    topics = {i.topic for i in cal.items}
    assert topics & {"Diamond Rings", "Gold Necklaces"}          # uses real offerings
    assert all(i.date.startswith("2026-06") or i.date.startswith("2026-07") for i in cal.items)
    assert all(0 <= (int(i.date[-2:])) for i in cal.items)        # valid dates


def test_day_offset_is_clamped_to_window():
    plan = _PlanResponse(items=[_PlanItem(day_offset=999, platform="instagram",
                                          content_type="reel", topic="X")])
    cal = build_strategy(_profile(), MockCaller({"content_strategy": plan}),
                         days=7, start_date="2026-06-20")
    assert cal.items[0].date == "2026-06-26"                      # clamped to day 6 (0..6)


def test_trends_are_woven_into_the_prompt():
    from trends import TrendItem
    mock = MockCaller({"content_strategy": _PlanResponse(items=[])})
    build_strategy(_profile(), mock, days=7,
                   trends=[TrendItem(title="Lab-grown diamonds surge", url="u", source="hn")])
    assert "Lab-grown diamonds surge" in mock.calls[0].user_prompt


def test_calendar_save_roundtrip(tmp_path: Path):
    cal = build_strategy(_profile(), None, days=7, start_date="2026-06-20")
    out = cal.save(tmp_path / "plan.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["business_name"] == "Glamira"
    assert data["days"] == 7 and isinstance(data["items"], list) and data["items"]


def test_llm_error_falls_back_to_deterministic_plan():
    # The strategy group raises -> build_strategy must still return a usable calendar.
    mock = MockCaller({}, raise_on_group={"content_strategy"})
    cal = build_strategy(_profile(), mock, days=10, start_date="2026-06-20")
    assert len(cal.items) >= 1
    assert {i.topic for i in cal.items} & {"Diamond Rings", "Gold Necklaces"}
