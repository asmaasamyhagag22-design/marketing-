"""U1 gate grading harness (benchmark.grade_u1). Hermetic — the deduction is stubbed; only the
grading + accuracy math is under test (the builder itself is covered by test_media_plan_builder)."""
from __future__ import annotations

import benchmark.grade_u1 as g
from media_plan.schemas import (
    CampaignObjective, Destination, EvidenceItem, EvidenceRef, FunnelStage, MetaObjective,
)


def _obj(objective=MetaObjective.SALES, destination=Destination.ONLINE_STORE, grounded=True):
    return CampaignObjective(
        objective=objective, destination=destination, funnel_stage=FunnelStage.BOFU,
        rationale="r", budget_allocation_pct=100.0,
        evidence=[EvidenceRef(claim="c", resolved=grounded,
                              evidence=[EvidenceItem(page_url="https://x", extractor="rule:x")])])


def test_load_env_never_overrides_existing(monkeypatch):
    """_load_env (entrypoint-only) must not clobber an already-set var and must not raise
    even if python-dotenv or the .env file is absent."""
    import os
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sentinel-project")
    g._load_env()
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "sentinel-project"


def test_match_objective_accepts_value_name_and_label():
    assert g.match_objective(MetaObjective.SALES, "OUTCOME_SALES")   # API value
    assert g.match_objective(MetaObjective.SALES, "SALES")           # enum name
    assert g.match_objective(MetaObjective.SALES, "Sales")           # label
    assert g.match_objective(MetaObjective.LEADS, "leads")
    assert not g.match_objective(MetaObjective.SALES, "Leads")       # wrong
    assert not g.match_objective(None, "Sales")                      # no deduction never matches


def test_match_destination_normalizes():
    assert g.match_destination(Destination.WHATSAPP, "whatsapp")
    assert g.match_destination(Destination.ONLINE_STORE, "online store")   # space -> underscore
    assert not g.match_destination(Destination.WHATSAPP, "phone_call")
    assert not g.match_destination(None, "whatsapp")


def test_summarize_computes_accuracies_and_gate():
    grades = [
        g.U1Grade("a", "Sales", "online_store", "OUTCOME_SALES", "online_store", True, True, True),
        g.U1Grade("b", "Leads", None, "OUTCOME_LEADS", "whatsapp", True, None, True),   # no dest label
        g.U1Grade("c", "Sales", "website", "OUTCOME_TRAFFIC", "website", False, True, True),  # obj wrong
    ]
    s = g.summarize(grades)
    assert s["graded"] == 3
    assert abs(s["objective_accuracy"] - 2 / 3) < 1e-9        # a,b match; c wrong
    assert s["destination_labeled"] == 2                       # a and c have dest labels
    assert s["destination_accuracy"] == 1.0                    # both dest matched
    assert s["combined_accuracy"] == 0.5                       # a both-ok, c obj-wrong -> 1/2
    assert s["passed"] is False                                # 0.667 < 0.80


def test_summarize_gate_passes_at_80pct():
    grades = [g.U1Grade(f"u{i}", "Sales", None, "OUTCOME_SALES", None, i < 4, None, True) for i in range(5)]
    s = g.summarize(grades)                                    # 4/5 = 80%
    assert s["objective_accuracy"] == 0.8 and s["passed"] is True


def test_grade_u1_scores_deduction_and_flags_missing_profile(monkeypatch):
    monkeypatch.setattr(g, "_labels", lambda: {
        "store": {"expected_objective": "Sales", "expected_destination": "online_store"},
        "clinic": {"expected_objective": "Leads", "expected_destination": "whatsapp"},
        "noprof": {"expected_objective": "Traffic", "expected_destination": None},
    })
    monkeypatch.setattr(g, "load_urls", lambda: {"urls": [
        {"id": "store", "url": "https://store"}, {"id": "clinic", "url": "https://clinic"},
        {"id": "noprof", "url": "https://noprof"}]})
    monkeypatch.setattr(g, "_profile_for",
                        lambda url: None if "noprof" in url else {"name": {"value": "X"}})

    monkeypatch.setattr(g, "_manifest_for", lambda url: None)
    monkeypatch.setattr(g, "build_campaign_objective",
                        lambda profile, caller=None, manifest=None: _obj(MetaObjective.SALES,
                                                                         Destination.ONLINE_STORE))

    grades = {gr.url_id: gr for gr in g.grade_u1()}
    assert grades["store"].objective_match is True and grades["store"].destination_match is True
    assert grades["clinic"].objective_match is False           # deduced SALES != expected Leads
    assert grades["noprof"].error and grades["noprof"].objective_match is False   # no cached profile -> miss
    assert g.summarize(list(grades.values()))["graded"] == 3
