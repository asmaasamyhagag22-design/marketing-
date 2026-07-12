# -*- coding: utf-8 -*-
"""Client-deliverable rubric F — the honesty surface ("what we don't know yet"). Hermetic.

Unknowns are DISPLAYED honestly, each naming the step that closes it; no red banners, no
fabrication. Failures are relocated to disclosure, never hidden."""
from __future__ import annotations

from dashboard.build import _honesty_surface


def test_standalone_and_no_voice_are_disclosed():
    comp = {"swot": {"mode": "standalone"}, "competitor_count": 0}
    mp = {"objectives": [{"objective": "OUTCOME_SALES",
                          "kpi_target": {"metric": "cost_per_purchase"}}]}
    html = _honesty_surface(comp, mp, {}, n_voice=0)
    assert "ما لا نعرفه بعد · What we don't know yet" in html
    assert "لم نؤكّد منافسين مباشرين بعد" in html           # standalone disclosed
    assert "لم نجمع آراء عملاء بعد" in html                 # no voice disclosed
    assert "إعلانات المنافسين الجارية غير متاحة" in html    # ads gap disclosed (blocked on Meta)
    assert "الرقم المستهدف للتكلفة لم يُحدَّد" in html       # null KPI target disclosed honestly
    # every gap names the closing step (advisor-gap channel), not just the problem
    assert "تأكيد قائمة المنافسين" in html and "Google-Maps" in html


def test_no_gaps_when_everything_is_present():
    comp = {"swot": {"mode": "competitive"}, "competitor_count": 3}
    mp = {"objectives": [{"objective": "OUTCOME_SALES",
                          "kpi_target": {"metric": "cost_per_purchase", "target_value": 55}}],
          "base_persona": {"age_range": {"value": "25-34", "evidence": [{"quote": "q"}]}}}
    html = _honesty_surface(comp, mp, {}, n_voice=5)
    # competitors present, voice present, KPI target present, persona evidenced -> only the
    # standing ads-availability gap remains (honest: that IS still unknown)
    assert "لم نؤكّد منافسين" not in html and "لم نجمع آراء عملاء" not in html
    assert "الرقم المستهدف للتكلفة لم يُحدَّد" not in html
    assert "إعلانات المنافسين الجارية غير متاحة" in html    # the one true remaining unknown


def test_no_red_banner_language():
    html = _honesty_surface({"swot": {"mode": "standalone"}}, {}, {}, 0)
    for word in ("error", "Error", "FAIL", "traceback", "Exception", "خطأ"):
        assert word not in html                            # failures are disclosure, never alarms
