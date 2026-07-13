# -*- coding: utf-8 -*-
"""T-TIER — WHY each competitor matched, shown on its card. Hermetic."""
from __future__ import annotations

from dashboard.build import _competitor_card, _tier_reasons


def test_tier_reasons_from_breakdown():
    bd = {"sub_vertical": 0.8, "audience_tier": 0.7, "size_similarity": 0.65,
          "proximity": 0.9, "language": 0.3}
    html = _tier_reasons(bd)
    assert "نفس المجال · same field" in html
    assert "نفس الشريحة السعرية · same price band" in html
    assert "حجم مماثل · similar size" in html
    assert "قريب منك · nearby" in html
    assert "same language" not in html          # 0.3 is below the match threshold


def test_web_path_breakdown_shows_no_false_chips():
    bd = {"sub_vertical": None, "proximity": None, "size_similarity": None,
          "audience_tier": None, "language": None, "total": 1.0}
    assert _tier_reasons(bd) == ""              # honest: no tier match on the web-search path


def test_card_prefers_tier_chips_else_search_reason():
    # Places peer with a real tier match -> chips, not the raw why string
    places = {"selection": {"name": "Clinic B", "website": "https://b.com", "peer_fit_score": 0.72,
                            "breakdown": {"sub_vertical": 0.8, "audience_tier": 0.7,
                                          "size_similarity": 0.7, "proximity": 0.8},
                            "why_selected": "type=doctor tier=mid dist=1.2km"}}
    card = _competitor_card(places)
    assert "نفس الشريحة السعرية" in card and "type=doctor" not in card   # jargon hidden
    # web peer with null breakdown -> the honest search reason still shows
    web = {"selection": {"name": "Shop A", "website": "https://a.com", "peer_fit_score": 1.0,
                         "breakdown": {"sub_vertical": None, "total": 1.0},
                         "why_selected": "web search peer (rank 1)"}}
    assert "web search peer (rank 1)" in _competitor_card(web)
