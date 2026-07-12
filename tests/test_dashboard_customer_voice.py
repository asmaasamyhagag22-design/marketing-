# -*- coding: utf-8 -*-
"""Customer voice + media plan ON the dashboard (owner directive 2026-07-12:
'أنا عايزة الشغل كله يترند في الداشبورد') — hermetic, no network.

The chain being pinned: saved review data -> full_run's own-voice themes -> SWOT items
(evidence: own-brand customer voice) -> the exported HTML renders a dedicated
'Customer voice — صوت العملاء' section with verbatim «quotes», and the U1 media plan is
auto-discovered next to the result file and rendered as a card."""
from __future__ import annotations

import json
from pathlib import Path

from dashboard.build import build_dashboard


def test_dashboard_renders_voice_section_and_media_plan_card(tmp_path):
    competitor = {
        "subject_url": "https://clinic.example/", "subject_category": "clinic",
        "competitor_count": 0, "competitors": [],
        "swot": {
            "mode": "competitive",
            "strengths": [{"text": "التمريض (nursing)",
                           "citation": ["own voice V1: «طاقم تمريض على أعلى مستوى»",
                                        "own voice V2: «مشرفة التمريض محترمة»"],
                           "evidence": "praise theme in own-brand customer voice",
                           "claim_strength": "validated"}],
            "weaknesses": [{"text": "الانتظار (waiting_time)",
                            "citation": ["own voice V3: «استنيت ساعتين»"],
                            "evidence": "complaint theme in own-brand customer voice",
                            "claim_strength": "directional_not_validated"}],
            "opportunities": [], "threats": [],
        },
        "tows": {"strategies": []},
    }
    media_plan = {
        "objectives": [{"objective": "OUTCOME_LEADS", "destination": "lead_form",
                        "funnel_stage": "bofu",
                        "rationale": "Booking form on site.",
                        "evidence": [{"claim": "c", "evidence": [], "resolved": True}],
                        "kpi_target": {"metric": "cost_per_lead"}}],
        "base_geo": {"mode": "radius", "center_address": "Cairo", "radius_km": 10},
    }
    cp = tmp_path / "clinic_result.json"
    cp.write_text(json.dumps(competitor, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "clinic_media_plan.json").write_text(
        json.dumps(media_plan, ensure_ascii=False), encoding="utf-8")

    out = build_dashboard(str(cp), out_path=str(tmp_path / "dash.html"))
    html = Path(out).read_text(encoding="utf-8")

    # the voice section is unmissable and carries the verbatim receipts
    assert "Customer voice — صوت العملاء" in html
    assert "طاقم تمريض على أعلى مستوى" in html and "استنيت ساعتين" in html
    # the media plan card was AUTO-DISCOVERED from the sibling file
    assert "Media plan — خطة الشراء الإعلاني" in html
    assert "OUTCOME_LEADS" in html and "cost_per_lead" in html
    assert "مؤكد بالأدلة" in html                      # resolved evidence -> the green badge
    assert "Cairo" in html and "10" in html            # geo radius rendered


def test_dashboard_without_voice_or_plan_stays_clean(tmp_path):
    competitor = {"subject_url": "https://x.example/", "competitor_count": 0,
                  "competitors": [], "swot": {"mode": "standalone", "strengths": [],
                                              "weaknesses": [], "opportunities": [], "threats": []},
                  "tows": {"strategies": []}}
    cp = tmp_path / "x_result.json"
    cp.write_text(json.dumps(competitor), encoding="utf-8")
    html = Path(build_dashboard(str(cp), out_path=str(tmp_path / "d.html"))).read_text(encoding="utf-8")
    assert "Customer voice" not in html and "Media plan —" not in html


def test_full_run_voice_files_match_by_slug_prefix(tmp_path):
    from competitor.full_run import _voice_files_for
    d = tmp_path / "fixtures"
    d.mkdir()
    (d / "alameda_hc.json").write_text("[]", encoding="utf-8")     # matches alameda-hc.com
    (d / "absa_gold_ar.json").write_text("[]", encoding="utf-8")   # must NOT match
    (d / "demo.json").write_text("[]", encoding="utf-8")           # too short / unrelated
    hits = _voice_files_for("https://www.alameda-hc.com/", dirs=[d])
    assert [f.name for f in hits] == ["alameda_hc.json"]
    assert _voice_files_for("https://unrelated-brand.com/", dirs=[d]) == []


def test_full_run_own_voice_themes_rows_and_gating(tmp_path, monkeypatch):
    # sanitized Maps fixture rows -> ABSA rows (own-brand) -> themed via MockCaller,
    # verbatim-substring gate still enforced end-to-end.
    from business_profile.llm.caller import MockCaller
    from competitor.full_run import _own_voice_themes
    from reviews.absa import AspectMention, _AbsaResponse

    d = tmp_path / "fixtures"
    d.mkdir()
    rows = [{"source": "google_maps", "source_url": "u", "author_hash": "x" * 16,
             "text": "استنيت ساعتين في العيادة", "lang": "ar",
             "scraped_at": "2026-07-12T10:00:00+00:00"},
            {"source": "google_maps", "source_url": "u", "author_hash": "y" * 16,
             "text": "الانتظار طويل جدا هنا", "lang": "ar",
             "scraped_at": "2026-07-12T10:00:00+00:00"}]
    (d / "myclinic.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("competitor.full_run._voice_files_for",
                        lambda url, dirs=None: [d / "myclinic.json"])
    mock = MockCaller({"absa_mentions": _AbsaResponse(mentions=[
        AspectMention(source_id="V1", aspect="waiting_time", polarity="complaint",
                      evidence_quote="استنيت ساعتين"),
        AspectMention(source_id="V2", aspect="waiting_time", polarity="complaint",
                      evidence_quote="الانتظار طويل جدا"),
    ])})
    themes = _own_voice_themes("https://myclinic.com/", {"category": {"value": "clinic"}},
                               lambda *a: None, caller=mock)
    assert len(themes) == 1
    t = themes[0]
    assert t.is_own_brand and t.polarity == "complaint" and len(t.support) == 2
    assert any("استنيت ساعتين" in c for c in t.support)   # the verbatim receipt travels
