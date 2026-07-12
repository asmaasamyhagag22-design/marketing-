# -*- coding: utf-8 -*-
"""Client-deliverable rubric C — strategy narrative in business language. Hermetic.

The two-letter TOWS codes, the posture enum, and the claim-strength badges are all
translated into plain bilingual words; no unexplained jargon reaches the client."""
from __future__ import annotations

import json

from dashboard.build import build_dashboard_html


def _doc(tmp_path):
    competitor = {
        "subject_url": "https://x/", "subject_category": "education", "competitor_count": 3,
        "competitors": [],
        "swot": {"mode": "competitive",
                 "strengths": [{"text": "Accredited programs", "citation": ["your site"],
                                "claim_strength": "validated"}],
                 "weaknesses": [{"text": "Few CTAs", "citation": ["peers avg 5.8"],
                                 "claim_strength": "directional_not_validated"}],
                 "opportunities": [], "threats": []},
        "tows": {"posture": "leverage",
                 "strategies": [{"type": "SO", "title": "Use accreditation to win enrolments",
                                 "description": "Lead with the accreditation."},
                                {"type": "WT", "title": "Add booking CTAs", "description": "d"}]},
    }
    cp = tmp_path / "x_result.json"
    cp.write_text(json.dumps(competitor, ensure_ascii=False), encoding="utf-8")
    return build_dashboard_html(str(cp))


def test_tows_codes_translated_to_plain_words(tmp_path):
    html = _doc(tmp_path)
    assert "الاستراتيجية — ماذا تفعل ولماذا · Strategy — what to do" in html
    assert "هاجِم · attack" in html          # SO -> plain
    assert "احترِس · protect" in html        # WT -> plain
    # the code chip stays as a compact reference, but never stands alone as the only label
    assert "Use accreditation to win enrolments" in html


def test_posture_is_explained_not_a_bare_enum(tmp_path):
    html = _doc(tmp_path)
    assert "الوضع الاستراتيجي · Your strategic stance" in html
    assert "وضعك التنافسي قوي" in html and "Strong position" in html
    assert "Strategic posture: leverage" not in html   # the old bare-enum line is gone


def test_claim_strength_legend_in_plain_words(tmp_path):
    html = _doc(tmp_path)
    assert "confirmed vs several peers" in html and "مؤكَّد" in html
    assert "one-source signal" in html and "مبدئي" in html
