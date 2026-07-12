# -*- coding: utf-8 -*-
"""Client-deliverable rubric H — the five-minute ordered read. Hermetic.

One scroll tells it in order: Market -> Strategy -> Plan -> Creative -> Calendar -> Gaps,
with a "start here" arc after the executive summary."""
from __future__ import annotations

import json


def _full(tmp_path):
    competitor = {
        "subject_url": "https://x/", "subject_category": "education", "competitor_count": 2,
        "competitors": [{"selection": {"name": "Peer", "website": "https://p/",
                                       "peer_fit_score": 0.5, "why_selected": "rank 1"},
                         "candidate": {"name": "Peer"}}],
        "swot": {"mode": "competitive", "strengths": [{"text": "S1", "citation": ["your profile"]}],
                 "weaknesses": [], "opportunities": [], "threats": []},
        "tows": {"posture": "leverage",
                 "strategies": [{"type": "SO", "title": "Do the thing"}],
                 "priority_actions": [{"rank": 1, "action": "Fix: X", "horizon": "now"}]},
        "profile": {"name": {"value": "Acme"}, "description": {"value": "We teach."}},
    }
    plan = {"business_name": "Acme", "days": 14,
            "items": [{"date": "2026-07-05", "platform": "instagram", "content_type": "reel",
                       "topic": "T", "hook": "H"}]}
    media_plan = {"objectives": [{"objective": "OUTCOME_LEADS", "destination": "lead_form",
                                  "funnel_stage": "bofu", "rationale": "r",
                                  "kpi_target": {"metric": "cost_per_lead"}}],
                  "base_geo": {"mode": "national"}}
    cp = tmp_path / "acme_result.json"
    cp.write_text(json.dumps(competitor, ensure_ascii=False), encoding="utf-8")
    pp = tmp_path / "p.json"
    pp.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "acme_media_plan.json").write_text(json.dumps(media_plan, ensure_ascii=False),
                                                   encoding="utf-8")
    from dashboard.build import build_dashboard_html
    return build_dashboard_html(str(cp), plan_path=str(pp))


def test_reading_arc_and_section_order(tmp_path):
    html = _full(tmp_path)
    # the "start here" arc is present, numbered, bilingual
    assert "arc-step" in html
    assert "السوق · Market" in html and "الخطة · Plan" in html and "ما لا نعرفه · Gaps" in html
    # the sections appear in the mandated arc order (one scroll, top to bottom)
    order = ["Executive summary", "Strengths, weaknesses", "Strategy — what to do",
             "Your ad plan, explained", "Content calendar", "What we don't know yet"]
    idx = [html.find(x) for x in order]
    assert -1 not in idx and idx == sorted(idx)
