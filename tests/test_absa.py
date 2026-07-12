# -*- coding: utf-8 -*-
"""ABSA (owner-approved design, R-5) — hermetic, MockCaller only.

The contract under test is the CODE-enforced grounding, not model behavior:
substring-rejection of non-verbatim quotes, the >=2 distinct-rows threshold, alien-aspect
rejection, and the deterministic R-5 routing (own praise -> S, own complaint -> W,
peer service-gap complaint -> O) through the single door synthesize_swot(themes=).
"""
from __future__ import annotations

import json
from pathlib import Path

from business_profile.llm.caller import MockCaller
from competitor.matrix import build_matrix
from competitor.swot import synthesize_swot
from reviews.absa import AspectMention, _AbsaResponse, extract_aspect_themes, themes_for_swot

_FX = json.loads((Path(__file__).resolve().parent.parent / "reviews" / "fixtures"
                  / "absa_gold_ar.json").read_text(encoding="utf-8"))
_ROWS = _FX["rows"]


def _m(source_id: str, aspect: str, polarity: str, quote: str) -> AspectMention:
    return AspectMention(source_id=source_id, aspect=aspect, polarity=polarity,
                         evidence_quote=quote)


def _caller(mentions) -> MockCaller:
    return MockCaller({"absa_mentions": _AbsaResponse(mentions=mentions)})


def test_gold_fixture_end_to_end_with_all_rejection_gates():
    mentions = [
        # own-brand waiting_time complaints — verbatim quotes (survive)
        _m("R2", "waiting_time", "complaint", "استنيت ساعتين"),
        _m("R3", "waiting_time", "complaint", "الانتظار طويل جدا"),
        _m("R6", "waiting_time", "complaint", "انتظار فوق الساعة"),
        # own praise staff x2 — survive
        _m("R4", "staff", "praise", "المعاملة ممتازة"),
        _m("R7", "staff", "praise", "المعاملة راقية"),
        # peer waiting_time x2 — survive
        _m("P1", "waiting_time", "complaint", "استنيت كتير اوي"),
        _m("P3", "waiting_time", "complaint", "تأخير ساعة"),
        # PARAPHRASED quote (not a substring of P2's text) -> substring-REJECTED
        _m("P2", "communication", "complaint", "لا أحد يرد إطلاقا"),
        # alien aspect (not in the clinic taxonomy) -> rejected
        _m("R1", "parking", "praise", "المكان نضيف"),
        # cites a row that doesn't exist -> rejected
        _m("R99", "waiting_time", "complaint", "انتظار"),
    ]
    themes = extract_aspect_themes(_ROWS, category=_FX["category"], caller=_caller(mentions))
    got = {(t.aspect, t.polarity, t.is_own_brand): t for t in themes}
    assert set(got) == {("waiting_time", "complaint", True), ("staff", "praise", True),
                        ("waiting_time", "complaint", False)}
    assert got[("waiting_time", "complaint", True)].support == ["R2", "R3", "R6"]
    assert got[("waiting_time", "complaint", False)].support == ["P1", "P3"]

    # the single door into SWOT (R-5 routing)
    rts = themes_for_swot(themes)
    sw = synthesize_swot(build_matrix({"name": {"value": "عيادة"}}, []), themes=rts)
    w = [i for i in sw.weaknesses if "waiting_time" in i.text]
    s = [i for i in sw.strengths if "staff" in i.text]
    o = [i for i in sw.opportunities if "waiting_time" in i.text]
    assert w and w[0].claim_strength == "validated" and len(w[0].citation) == 3
    assert s and "own-brand" in s[0].evidence
    assert o and "Peers are criticized" in o[0].text   # peer service gap -> Opportunity
    # every citation carries a verbatim quote (the audit trail)
    assert any("«" in c for c in w[0].citation)


def test_fabricated_quotes_are_rejected_even_in_numbers():
    mentions = [
        _m("R2", "waiting_time", "complaint", "انتظرت ساعتين"),      # paraphrase of R2
        _m("R6", "waiting_time", "complaint", "الانتظار ساعة"),      # not a substring of R6
    ]
    assert extract_aspect_themes(_ROWS, category="clinic", caller=_caller(mentions)) == []


def test_single_support_stays_below_the_threshold():
    mentions = [_m("R2", "waiting_time", "complaint", "استنيت ساعتين")]
    assert extract_aspect_themes(_ROWS, category="clinic", caller=_caller(mentions)) == []


def test_no_caller_and_empty_rows_are_valid_and_silent():
    assert extract_aspect_themes(_ROWS, category="clinic", caller=None) == []
    assert extract_aspect_themes([], category="clinic", caller=_caller([])) == []


def test_unknown_category_uses_the_universal_taxonomy():
    mentions = [
        _m("R2", "waiting_time", "complaint", "استنيت ساعتين"),
        _m("R6", "waiting_time", "complaint", "انتظار فوق الساعة"),
        # doctor_competence is clinic-only — under the universal default it's alien
        _m("R1", "doctor_competence", "praise", "الدكتور شاطر جدا"),
        _m("P1", "doctor_competence", "praise", "الدكتور كويس"),
    ]
    themes = extract_aspect_themes(_ROWS, category="salon-of-unknown-kind",
                                   caller=_caller(mentions))
    assert {(t.aspect, t.is_own_brand) for t in themes} == {("waiting_time", True)}
