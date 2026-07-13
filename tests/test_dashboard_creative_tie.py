# -*- coding: utf-8 -*-
"""Client-deliverable rubric D — every creative labelled with the strategy line, audience,
and funnel stage it serves. No orphan creatives. Hermetic."""
from __future__ import annotations

import json


def _doc(tmp_path, with_reel=True):
    competitor = {
        "subject_url": "https://x/", "subject_category": "education", "competitor_count": 2,
        "competitors": [], "swot": {"mode": "competitive",
                                    "strengths": [{"text": "S"}], "weaknesses": [],
                                    "opportunities": [], "threats": []},
        "tows": {"posture": "leverage", "strategies": [{"type": "SO", "title": "Win enrolments"}],
                 "priority_actions": [{"rank": 1, "action": "Leverage: Bridge the talent gap",
                                       "horizon": "now"}]},
        "profile": {"name": {"value": "NTI"}, "description": {"value": "We train."}},
    }
    media_plan = {"objectives": [{"objective": "OUTCOME_LEADS", "destination": "lead_form",
                                  "funnel_stage": "bofu", "kpi_target": {"metric": "cost_per_lead"}}],
                  "base_persona": {"interests": [{"claim": "the brand's audience: fresh graduates"}]},
                  "base_geo": {"mode": "national"}}
    cp = tmp_path / "nti_result.json"
    cp.write_text(json.dumps(competitor, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "nti_media_plan.json").write_text(json.dumps(media_plan, ensure_ascii=False),
                                                  encoding="utf-8")
    reel = None
    if with_reel:
        reel = tmp_path / "r.mp4"
        reel.write_bytes(b"\x00\x00\x00\x18ftypmp42")   # a tiny valid-enough file for data-uri
    from dashboard.build import build_dashboard_html
    return build_dashboard_html(str(cp), reel_path=str(reel) if reel else None)


def test_creative_is_labelled_with_strategy_audience_funnel(tmp_path):
    html = _doc(tmp_path, with_reel=True)
    assert "الإبداع — مربوط باستراتيجيتك · Creative — tied to your strategy" in html
    assert "يخدم استراتيجيتك · serves your strategy" in html
    # the three ties, all from the same plan the deliverable shows
    assert "Bridge the talent gap" in html and "Leverage:" not in html.split("tie-chip")[1]
    assert "تحويل · BOFU" in html                       # funnel stage
    assert "fresh graduates" in html                    # audience


def test_no_creative_section_without_assets(tmp_path):
    html = _doc(tmp_path, with_reel=False)
    assert "الإبداع — مربوط باستراتيجيتك" not in html    # no orphan section when nothing to show
