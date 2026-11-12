"""Exercise refresh through the canonical HTTP, review and persistence boundaries."""
import time
from uuid import UUID

import pytest

from test_app_review_graph import application, begin
from test_review_workflow import approvals, database, decision
from workflows.synthetic import brand, objective


def replace_profile(service, data, payload=None, *, source_capture=None):
    from db.services import ProfileData, ScrapeSuccess

    actor = UUID(data["actor"])
    domain = data["domain"]
    job = service.create_user_job(owner_user_id=actor, requested_domain_key=domain)
    service.claim_job(job_id=job.id, worker_id=str(job.id), lease_seconds=600)
    return service.commit_scrape_success(ScrapeSuccess(
        domain_key=domain, user_id=actor, job_id=job.id, worker_id=str(job.id),
        profile=ProfileData(
            payload=brand(domain)["_profile"] if payload is None else payload,
            schema_version=1),
        source_url="https://studio.example.test",
        display_name="Refreshed Studio",
        source_capture=source_capture,
    ))


def brand_document(client, headers, data):
    return client.get(f"/api/brands/{data['domain']}", headers=headers).json()


def approve_strategy(client, headers, data):
    review = begin(client, headers, data)
    assert review.status_code == 200, review.text
    state = review.json()
    assert state["status"] == "NEEDS_REVIEW", state
    return client.post(f"/api/review/{state['workflow_id']}/resume",
                       headers=headers, json=decision(state))


def test_refresh_blocks_old_approval_review_and_admission(application, monkeypatch):
    from sqlalchemy import func, select
    from db.models import Run, UsageRecord

    from api.routes import generate

    client, headers, service, _, data, _ = application
    render_reservations = []

    def fake_emit(*args, **kwargs):
        with service._uow_factory() as uow:
            reserved = uow.session.scalar(select(Run.reserved_usd).where(
                Run.created_by_user_id == UUID(data["actor"]), Run.kind == "poster"))
        render_reservations.append(float(reserved))
        return {}

    monkeypatch.setattr(generate, "_emit", fake_emit)
    monkeypatch.setenv("ADZY_POSTER_RESERVATION_USD", "0.6")
    monkeypatch.setenv("ADZY_POSTER_BUDGET_USD", "10")
    approved = approve_strategy(client, headers, data)
    assert approved.status_code == 200 and approved.json()["status"] == "READY_FOR_CREATIVE"
    original = brand_document(client, headers, data)
    original_rows = approvals(service, data)
    replace_profile(service, data)
    document = brand_document(client, headers, data)
    subject = {"domain_key": data["domain"], "strategy_version_id": data["subject"]}
    state = approved.json()
    responses = {
        "review": client.get(f"/api/review/{state['workflow_id']}", headers=headers),
        "swot_approval": client.post("/api/swot/approve", headers=headers, json={
            "domain_key": data["domain"], "swot_run_id": original["swot_run_id"]}),
        "strategy_approval": client.post("/api/strategy/decide", headers=headers, json={
            "domain_key": data["domain"], "strategy_run_id": data["subject"],
            "decision": "approved"}),
        "contract": client.post("/api/poster/contract", headers=headers, json=subject),
        "admission": client.post("/api/generate", headers=headers, json={
            **subject, "operation_key": "profile_refresh_stale"}),
    }
    with service._uow_factory() as uow:
        operations, reserved = uow.session.execute(
            select(func.count(), func.coalesce(func.sum(Run.reserved_usd), 0)).where(
                Run.created_by_user_id == UUID(data["actor"]), Run.kind == "poster")).one()
        usage = uow.session.scalar(select(func.count()).select_from(UsageRecord).join(
            Run, Run.id == UsageRecord.run_id).where(Run.created_by_user_id == UUID(data["actor"])))
    actual = {
        **{name: response.status_code for name, response in responses.items()},
        "swot_approved": document["swot_approved"],
        "strategy_approval_state": document["strategy_approval_state"],
        "poster_runs": operations,
        "reserved_usd": float(reserved),
        "usage_records": usage,
        "render_reservations_usd": render_reservations,
    }
    assert actual == {
        "review": 409, "swot_approval": 409, "strategy_approval": 409, "contract": 409,
        "admission": 409, "swot_approved": False, "strategy_approval_state": "stale",
        "poster_runs": 0, "reserved_usd": 0, "usage_records": 0, "render_reservations_usd": [],
    }, actual
    assert document["strategy_candidate"]["run_id"] == data["subject"]
    assert responses["review"].json()["detail"]["code"] == "STALE_SUBJECT"
    for action in ("contract", "admission"):
        assert responses[action].json()["detail"]["code"] == "STRATEGY_PROFILE_CHANGED"
    assert [row.id for row in approvals(service, data)] == [row.id for row in original_rows]


def terminal(client, headers, start):
    assert start.status_code == 200, start.text
    job_id = start.json()["job_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}", headers=headers)
        response.raise_for_status()
        job = response.json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(.02)
    pytest.fail("Analysis job did not finish")


def test_strategy_read_from_old_profile_cannot_commit_as_new(application, monkeypatch):
    import strategy.positioning as positioning

    client, headers, service, _, data, _ = application
    original = positioning.build_positioning_strategy

    def build_while_profile_changes(*args, **kwargs):
        result = original(*args, **kwargs)
        replace_profile(service, data)
        return result

    monkeypatch.setattr(positioning, "build_positioning_strategy", build_while_profile_changes)
    outcome = terminal(client, headers, client.post("/api/strategy/generate", headers=headers,
        json={"domain_key": data["domain"], "objective": objective()}))
    document = brand_document(client, headers, data)
    assert (outcome["status"], document["strategy_run_id"]) == ("error", data["subject"])
    assert "Brand evidence changed" in outcome["error"]


def test_swot_read_from_old_profile_cannot_commit_as_new(application, monkeypatch):
    from api import webapp_analysis

    client, headers, service, _, data, _ = application
    original = brand_document(client, headers, data)

    def swot_while_profile_changes(current):
        replace_profile(service, data)
        return {"has_swot": True, "swot": {"marker": "old profile"}}

    monkeypatch.setattr(webapp_analysis, "generate_swot", swot_while_profile_changes)
    outcome = terminal(client, headers, client.post("/api/swot/generate", headers=headers,
        json={"domain_key": data["domain"]}))
    document = brand_document(client, headers, data)
    assert (outcome["status"], document["swot_run_id"]) == ("error", original["swot_run_id"])
    assert "Brand evidence changed" in outcome["error"]


def test_pending_review_stays_stale_after_refresh_without_new_approval(application):
    client, headers, service, _, data, _ = application
    state = begin(client, headers, data).json()
    assert state["status"] == "NEEDS_REVIEW"
    replace_profile(service, data)
    response = client.post(f"/api/review/{state['workflow_id']}/resume",
                           headers=headers, json=decision(state))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "STALE_SUBJECT"
    assert not approvals(service, data)


def test_refreshed_profile_with_missing_proof_stays_blocked(application, monkeypatch):
    from api import webapp_analysis

    client, headers, service, _, data, _ = application
    refreshed = brand(data["domain"])
    refreshed["_profile"]["trust_signals"] = []
    replace_profile(service, data, refreshed["_profile"])

    def swot_fixture(document):
        assert not document["_profile"]["trust_signals"]
        return {"has_swot": True, "swot": {"summary": "Refreshed fixture"},
                "_full_result": refreshed["_full_result"]}

    monkeypatch.setattr(webapp_analysis, "generate_swot", swot_fixture)
    target = {"domain_key": data["domain"]}
    assert terminal(client, headers, client.post(
        "/api/swot/generate", headers=headers, json=target))["status"] == "done"
    document = brand_document(client, headers, data)
    assert not document["swot_approved"] and not document["swot_stale"]
    swot = client.post("/api/swot/approve", headers=headers,
                       json={**target, "swot_run_id": document["swot_run_id"]})
    assert swot.status_code == 200, swot.text
    assert terminal(client, headers, client.post("/api/strategy/generate", headers=headers,
        json={**target, "objective": objective()}))["status"] == "done"
    candidate = brand_document(client, headers, data)["strategy_candidate"]
    assert candidate["run_id"] != data["subject"]
    assert not candidate["profile_stale"] and not candidate["eligible_for_approval"]
    assessment = candidate["research_sufficiency_assessment"]
    assert "req_reason_to_believe" in assessment["blocking_requirement_ids"]
    review = begin(client, headers, {**data, "subject": candidate["run_id"]}).json()
    assert review["status"] == "BLOCKED" and review["creative_contract"] is None
    approved = client.post("/api/strategy/decide", headers=headers, json={
        **target, "strategy_run_id": candidate["run_id"], "decision": "approved"})
    assert approved.status_code == 409
    assert not approvals(service, {**data, "subject": candidate["run_id"]})
