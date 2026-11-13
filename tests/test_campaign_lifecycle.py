from datetime import datetime, timedelta, timezone

from workflows.campaign_eval import case_set, case_source, review_input, run_case, release_decision
from workflows.campaign_monitor import report
from workflows.campaign_telemetry import CampaignTrace
from workflows.telemetry import Telemetry


def test_frozen_replay_release_and_causal_comparison():
    cases, bindings, dataset_id = case_set()
    rows = {release: [
        run_case(case, binding, dataset_id, release, Telemetry())
        for case, binding in zip(cases, bindings, strict=True)
    ] for release in ("stable", "candidate")}
    gate = release_decision(rows["stable"], rows["candidate"])
    assert not gate["blockers"]
    assert gate["default_release"] == "stable"
    assert {row["case"] for row in gate["restored_edits"]} == {"osm-local-knowledge", "nandos-wrap"}
    for result in rows["candidate"]:
        assert result["version"]["guardrails"]["policy"] == "campaign-copy@2"
        assert result["fixtures"]["snapshot_id"] and result["eval_set_id"] == dataset_id
        for edit in result["edits"]:
            if edit["critical"]:
                assert edit["classification"] == "EXPECTED" and not edit["accepted"]
    failure = next(row for row in rows["stable"] if row["case_id"] == "nandos-page-cap")
    assert failure["source_mode"] == "simulated_transport"
    assert failure["journey"] == "BLOCKED" and failure["fetch"] == ["PAGE_TOO_LARGE"]


def test_candidate_review_follows_saved_version_after_rollback(monkeypatch):
    from strategy.campaign_planner import PlanInput, build_plan, review_draft
    from strategy.campaign_v2 import CampaignConflict
    import pytest

    case = next(row for row in case_set()[0] if row["id"] == "osm-local-knowledge")
    request = PlanInput.model_validate(case["input"])
    monkeypatch.setenv("ADZY_CAMPAIGN_EDITIONS_FILE", "")
    with case_source(case) as (load, clock, mode):
        monkeypatch.setenv("ADZY_CAMPAIGN_RELEASE", "candidate")
        original = build_plan(request, "OpenStreetMap", load, clock, trace=CampaignTrace(mode=mode))
        monkeypatch.setenv("ADZY_CAMPAIGN_RELEASE", "stable")
        fresh = build_plan(request, "OpenStreetMap", load, clock, trace=CampaignTrace(mode=mode))
    review = review_input(original["brief"], case["edits"][0])
    preserved = review_draft(original, review)
    assert preserved["package"]["copy"]["headline"] == "Local Knowledge"
    assert preserved["planner"]["version"] == original["planner"]["version"]
    assert preserved["planner"]["snapshot_id"] == original["planner"]["snapshot_id"]
    for draft in (fresh, {**original, "planner": {k: v for k, v in original["planner"].items() if k != "version"}}):
        with pytest.raises(CampaignConflict, match="COPY_REQUIRES_EVIDENCE_REVIEW"):
            review_draft(draft, review)


def test_monitor_counts_distinct_runs_and_requires_enough_latency_samples():
    now = datetime.now(timezone.utc)
    base = {"stage": "campaign.fetch", "source_mode": "simulated_transport", "status": "ERROR",
            "reason": "PAGE_TOO_LARGE", "at": now.isoformat(), "elapsed_ms": 1}
    rows = [{**base, "trace_id": "first"}] * 20
    rows.append({**base, "trace_id": "second", "elapsed_ms": 4})
    rows.append({**base, "trace_id": "old", "at": (now - timedelta(minutes=6)).isoformat()})
    rows.append({**base, "trace_id": "public", "source_mode": "public_http"})
    assert report(rows, end=now)["alerts"] == []
    rows.append({**base, "trace_id": "third", "elapsed_ms": 5})
    result = report(rows, end=now)
    assert result["alerts"][0]["trace_ids"] == ["first", "second", "third"]
    assert result["metrics"]["simulated_transport"]["latency"]["campaign.fetch"] == {"n": 22, "p95_ms": 4}
    assert result["metrics"]["public_http"]["latency"]["campaign.fetch"] == {"n": 1, "p95_ms": None}


def test_campaign_telemetry_does_not_emit_raw_reasons(caplog):
    import logging
    import pytest
    from strategy.campaign_research import ResearchGap
    from strategy.campaign_v2 import CampaignConflict
    from workflows.campaign_monitor import events

    private = "PRIVATE_EMAIL@EXAMPLE.ORG"

    def fail(url, timeout):
        raise ResearchGap(private)

    telemetry = Telemetry()
    telemetry.correlate("test-workflow")
    trace = CampaignTrace(telemetry, emit=True)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        with pytest.raises(ResearchGap):
            trace.loader(fail)(f"https://example.org/{private}", 2)
        with pytest.raises(CampaignConflict):
            with trace.stage("campaign.verify"):
                raise CampaignConflict(private)
    assert private not in caplog.text
    assert [row["reason"] for row in events(caplog.messages)] == ["UNKNOWN", "UNKNOWN"]
