# -*- coding: utf-8 -*-
"""Client-deliverable rubric G+ — zero raw internals + RTL bilingual. Hermetic."""
from __future__ import annotations

import json

from dashboard.build import _clean_citation, build_dashboard_html


def test_citation_cleaner_removes_internals():
    assert _clean_citation("value_propositions") == "قيمك المعلنة · your value props"
    assert _clean_citation("trust_signals") == "شارات الثقة · your trust badges"
    assert _clean_citation("readiness.swot_quality_signals.tagline=false").startswith("readiness")
    assert "web: naceweb.org" in _clean_citation("https://www.naceweb.org/x/y")
    # a real human phrase passes through untouched
    assert _clean_citation("4/4 peers also lack it") == "4/4 peers also lack it"


def test_standalone_page_is_rtl_arabic():
    competitor = {"subject_url": "https://x/", "competitor_count": 0, "competitors": [],
                  "swot": {"mode": "standalone",
                           "strengths": [{"text": "S", "citation": ["value_propositions"],
                                          "claim_strength": "internally_supported"}],
                           "weaknesses": [], "opportunities": [], "threats": []},
                  "tows": {"strategies": []},
                  "profile": {"name": {"value": "Acme"}}}
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        cp = f"{td}/x_result.json"
        with open(cp, "w", encoding="utf-8") as f:
            json.dump(competitor, f, ensure_ascii=False)
        html = build_dashboard_html(cp, standalone=True)
    assert 'lang="ar" dir="rtl"' in html               # RTL root for the Arabic-primary deliverable
    assert "Sakkal Majalla" in html or "Segoe UI" in html   # Arabic-capable font stack
    assert "قيمك المعلنة" in html and "value_propositions" not in html   # no snake_case leak
