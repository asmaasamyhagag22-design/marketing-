# -*- coding: utf-8 -*-
"""Competitor never-fabricate contract hardening (2026-07-05 audit).

- TOWS grounding gate fails CLOSED: a ledger error swaps in the grounded template instead
  of shipping the LLM's UNVERIFIED strategy text through the moat.
- The SERP peer-relevance judge's keep-list is REQUIRED, so an omitted judgment can't be
  read as pydantic's default [] and used to silently drop every real peer; an explicit
  empty list is still a genuine reject-only "keep none".

Hermetic: fake ledger / fake judge caller, no network / no LLM.
"""
from types import SimpleNamespace

from competitor.tows import _text_is_grounded
from competitor.web_discovery import SerpWebDiscoveryEngine
from competitor.models import Candidate, CompetitorProfile, SelectionRecord


# --- TOWS: fail CLOSED on a ledger error --------------------------------------------------
class _Verdict:
    def __init__(self, sourced):
        self.sourced = sourced


def test_tows_text_grounded_no_ledger_passes():
    assert _text_is_grounded("anything", None) is True


def test_tows_text_grounded_all_sourced_true():
    led = SimpleNamespace(audit_text=lambda t: [_Verdict(True)])
    assert _text_is_grounded("2 awards", led) is True


def test_tows_text_grounded_unsourced_false():
    led = SimpleNamespace(audit_text=lambda t: [_Verdict(False)])
    assert _text_is_grounded("#1 in Egypt", led) is False


def test_tows_gate_fails_closed_on_ledger_error():
    def boom(_t):
        raise RuntimeError("ledger blew up")
    led = SimpleNamespace(audit_text=boom)
    # fail CLOSED -> not grounded -> caller uses the grounded template (no unverified LLM text)
    assert _text_is_grounded("Leverage our #1 award", led) is False


# --- SERP peer-relevance judge ------------------------------------------------------------
def _peer(name, site):
    cand = Candidate(place_id="", name=name)
    sel = SelectionRecord(place_id="", name=name, website=site, peer_fit_score=1.0,
                          breakdown={}, why_selected="web peer (rank 1)")
    return CompetitorProfile(candidate=cand, selection=sel)


def _engine(judge):
    return SerpWebDiscoveryEngine(provider=None, judge_caller=judge)


def test_judge_keeps_the_indices_it_returns():
    peers = [_peer("A", "https://a.com/"), _peer("B", "https://b.com/"),
             _peer("C", "https://c.com/")]
    judge = lambda s, u, m, group_name=None: (SimpleNamespace(keep_indices=[0, 2]), {})  # noqa: E731
    kept = _engine(judge)._judge_relevance({"name": {"value": "X"}}, peers)
    assert [p.candidate.name for p in kept] == ["A", "C"]


def test_judge_explicit_empty_drops_all_reject_only():
    peers = [_peer("A", "https://a.com/")]
    judge = lambda s, u, m, group_name=None: (SimpleNamespace(keep_indices=[]), {})  # noqa: E731
    assert _engine(judge)._judge_relevance({"name": {"value": "X"}}, peers) == []


def test_judge_error_keeps_all_graceful():
    peers = [_peer("A", "https://a.com/"), _peer("B", "https://b.com/")]

    def judge(s, u, m, group_name=None):
        raise RuntimeError("api down")
    kept = _engine(judge)._judge_relevance({"name": {"value": "X"}}, peers)
    assert len(kept) == 2                       # judge failure never breaks discovery


def test_no_judge_keeps_all():
    peers = [_peer("A", "https://a.com/")]
    assert _engine(None)._judge_relevance({"name": {"value": "X"}}, peers) == peers
