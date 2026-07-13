# -*- coding: utf-8 -*-
"""Round-2 D — capability census: the dropped selling lines get a home + the "what's
included" strip with a logs link. Hermetic."""
from __future__ import annotations

import json

from dashboard.build import _brand_assets, _capability_census, build_dashboard_html


def test_brand_assets_surface_trust_valueprops_offerings():
    prof = {"trust_signals": [{"value": "Accredited by the Supreme Council of Universities"},
                              {"value": "ITU 10-year certificate"}],
            "value_propositions": [{"value": "Workforce-ready graduates"}],
            "offerings": [{"name": {"value": "Fiber Networks Essentials"}}, {"name": "Business Skills"}]}
    html = _brand_assets(prof)
    assert "شارات الثقة والاعتمادات · Trust" in html
    assert "Accredited by the Supreme Council of Universities" in html   # the credibility spine
    assert "لماذا يختارك العملاء" in html and "Workforce-ready graduates" in html
    assert "Fiber Networks Essentials" in html and "Business Skills" in html


def test_brand_assets_empty_when_nothing():
    assert _brand_assets({}) == ""


def test_capability_census_checklist_and_logs_link():
    comp = {"profile": {"name": "X"}, "competitor_count": 3,
            "swot": {"strengths": [{"text": "s"}]}}
    html = _capability_census(comp, has_plan=True, has_creative=False,
                              run_cost={"cost_usd": 0.11, "llm_calls": 7})
    assert "✓" in html and "تحليل SWOT · SWOT analysis" in html
    assert "خطة الإعلان · Ad plan" in html                # has_plan True -> checked
    assert "○ الإبداع" in html                            # has_creative False -> open circle, no red
    assert "≈ $0.11" in html and "7 نداء ذكاء" in html    # telemetry cost surfaced
    assert "سجل التشغيل" in html                          # logs link
    # never a red/error state
    for w in ("error", "FAIL", "خطأ", "Exception"):
        assert w not in html


def test_census_in_page(tmp_path):
    competitor = {"subject_url": "https://x/", "competitor_count": 1, "competitors": [],
                  "swot": {"mode": "competitive", "strengths": [{"text": "S"}], "weaknesses": [],
                           "opportunities": [], "threats": []}, "tows": {"strategies": []},
                  "profile": {"name": {"value": "NTI"},
                              "trust_signals": [{"value": "Accredited"}]}}
    cp = tmp_path / "x_result.json"
    cp.write_text(json.dumps(competitor, ensure_ascii=False), encoding="utf-8")
    html = build_dashboard_html(str(cp))
    assert "ما وجدناه في موقعك" in html and "Accredited" in html
    assert "كل خطوة موثّقة في سجل التشغيل" in html
