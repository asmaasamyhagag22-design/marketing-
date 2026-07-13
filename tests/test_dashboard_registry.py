# -*- coding: utf-8 -*-
"""Competitor-registry diff ON the dashboard (T-REGISTRY) — hermetic.

The stable baseline is visible; disappeared peers are flagged (not deleted); newcomers show
as PENDING owner approval (HITL for identity), never silently added."""
from __future__ import annotations

import json

from dashboard.build import _registry_panel, build_dashboard_html


def test_registry_panel_shows_diff_states():
    comp = {"registry_diff": {
        "still_present": [{"key": "a.com", "name": "Peer A"}],
        "disappeared": [{"key": "b.com", "name": "Peer B"}],
        "new_pending": [{"key": "c.com", "name": "Peer C"}]}}
    html = _registry_panel(comp)
    assert "سجل المنافسين" in html and "stable, changes only with your approval" in html
    assert "Peer A" in html and "ثابت · present" in html
    assert "Peer B" in html and "اختفى · disappeared" in html and "kept for your review" in html
    assert "Peer C" in html and "بانتظار موافقتك" in html      # pending, not auto-added


def test_no_panel_on_first_run_or_no_drift():
    assert _registry_panel({"registry_diff": None}) == ""       # first run
    assert _registry_panel({"registry_diff": {"still_present": [{"key": "a"}],
                                              "disappeared": [], "new_pending": []}}) == ""


def test_registry_panel_in_page(tmp_path):
    competitor = {"subject_url": "https://x/", "competitor_count": 1, "competitors": [],
                  "swot": {"mode": "competitive", "strengths": [{"text": "S"}], "weaknesses": [],
                           "opportunities": [], "threats": []},
                  "tows": {"strategies": []},
                  "registry_diff": {"still_present": [], "disappeared": [],
                                    "new_pending": [{"key": "n.com", "name": "New Rival"}]}}
    cp = tmp_path / "x_result.json"
    cp.write_text(json.dumps(competitor, ensure_ascii=False), encoding="utf-8")
    html = build_dashboard_html(str(cp))
    assert "New Rival" in html and "pending your approval" in html
