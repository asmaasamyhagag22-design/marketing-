"""Measure advisory observations at the PostgreSQL and HTTP boundaries."""
from types import SimpleNamespace
from uuid import UUID

from test_app_review_graph import application
from test_profile_refresh_review import approve_strategy, brand_document, replace_profile
from test_review_workflow import approvals, database
from workflows.synthetic import brand, field, source_capture


def assert_historical_only(client, headers, data, report, old_approval_ids, service):
    doc = brand_document(client, headers, data)
    candidate = doc["strategy_candidate"]
    assert candidate["review_shadow"] == report
    assert report["mode"] == "shadow" and report["strategy_run_id"] == data["subject"]
    assert report["to_profile_snapshot_id"] == doc["profile_snapshot_id"]
    assert doc["strategy_approval_state"] == "stale" and not doc["swot_approved"]
    contract = client.post("/api/poster/contract", headers=headers, json={
        "domain_key": data["domain"], "strategy_version_id": data["subject"]})
    assert contract.status_code == 409
    admission = client.post("/api/generate", headers=headers, json={
        "domain_key": data["domain"], "strategy_version_id": data["subject"],
        "operation_key": "shadow_stale_probe"})
    assert admission.status_code == 409
    assert admission.json()["detail"]["code"] == "STRATEGY_PROFILE_CHANGED"
    approved = client.post("/api/strategy/decide", headers=headers, json={
        "domain_key": data["domain"], "strategy_run_id": data["subject"], "decision": "approved"})
    assert approved.status_code == 409
    assert [row.id for row in approvals(service, data)] == old_approval_ids


def test_shadow_skip_and_changes_compare_against_approved_profile(application):
    client, headers, service, _, data, _ = application
    approval = approve_strategy(client, headers, data)
    assert approval.status_code == 200 and approval.json()["status"] == "READY_FOR_CREATIVE"
    old_ids = [row.id for row in approvals(service, data)]
    original = brand_document(client, headers, data)["profile_snapshot_id"]
    source = brand(data["domain"])
    stable = replace_profile(service, data, source["_profile"], source_capture=source_capture(source))
    stable_report = stable.run.output["review_shadow"]
    assert stable_report["decision"] == "SKIP"
    assert stable_report["from_profile_snapshot_id"] == original
    assert_historical_only(client, headers, data, stable_report, old_ids, service)

    source["_profile"]["trust_signals"][0] = field("Published guided specialist onboarding checklist")
    changed_capture = source_capture(source)
    changed = replace_profile(service, data, source["_profile"], source_capture=changed_capture)
    report = changed.run.output["review_shadow"]
    assert report["decision"] == "REVIEW"
    assert report["from_profile_snapshot_id"] == original
    change, = report["changes"]
    proof, = [item for item in change["impacts"] if item["part"] == "Reason to believe"]
    assert change["page_url"] == "https://studio.example.test/process"
    assert proof["before_quote"] == "Published guided specialist onboarding process"
    assert proof["current_excerpt"] == "Published guided specialist onboarding checklist"
    assert proof["evidence_id"] and proof["claim_id"]

    # Another scrape equal to the last observation remains different from the approved evidence.
    repeated = replace_profile(service, data, source["_profile"], source_capture=changed_capture)
    report = repeated.run.output["review_shadow"]
    assert report["from_profile_snapshot_id"] == original and report["decision"] == "REVIEW"
    assert_historical_only(client, headers, data, report, old_ids, service)

    from api.user_auth import issue_token
    stranger = service.create_user(email="shadow-stranger@example.invalid", hashed_password="disabled")
    foreign = client.get(f"/api/brands/{data['domain']}",
                         headers={"Authorization": "Bearer " + issue_token(str(stranger.id))})
    assert foreign.status_code == 404


def test_missing_capture_and_comparison_database_error_leave_scrape_successful(application, monkeypatch):
    from sqlalchemy import text
    from db.repositories import RunRepository

    client, headers, service, _, data, _ = application
    assert approve_strategy(client, headers, data).status_code == 200
    old_ids = [row.id for row in approvals(service, data)]
    missing = replace_profile(service, data)
    report = missing.run.output["review_shadow"]
    assert report["decision"] == "UNKNOWN" and "CAPTURE_MISSING" in report["reasons"]
    assert_historical_only(client, headers, data, report, old_ids, service)

    def unavailable(repo, **kwargs):
        repo.session.execute(text("SELECT 1 / 0"))

    monkeypatch.setattr(RunRepository, "scrape_for_profile", unavailable)
    failed_comparison = replace_profile(service, data)
    job = service.job_for_user(job_id=failed_comparison.job.id, user_id=UUID(data["actor"]))
    assert job.status == "succeeded"
    report = failed_comparison.run.output["review_shadow"]
    assert report["decision"] == "UNKNOWN" and report["reasons"] == ["SHADOW_COMPARISON_UNAVAILABLE"]
    assert_historical_only(client, headers, data, report, old_ids, service)


def test_capture_tracks_api_material_even_when_dom_is_identical():
    from scraper.source_capture import source_capture as capture_manifest
    from strategy.positioning.refresh_shadow import compare_captures

    url = "https://fixture.example.test/prices"
    block = SimpleNamespace(text="Price 40 EUR", tag="api")
    page = SimpleNamespace(http_status=200, failures=[], final_url=url, content_hash="a" * 64,
                           viewport_width=1280, viewport_height=800, text_blocks=[block])
    manifest = SimpleNamespace(pages=[page], failures=[], deep_search=None)
    before = capture_manifest(manifest)
    block.text = "Price 55 EUR"
    after = capture_manifest(manifest)
    dependency = {"page_url": url, "before_quote": "Price 40 EUR"}
    assert compare_captures(before, after, [dependency])["decision"] == "REVIEW"
    page.http_status = 503
    incomplete = capture_manifest(manifest)
    assert compare_captures(before, incomplete, [dependency])["decision"] == "UNKNOWN"


def test_invalid_fingerprint_cannot_make_capture_look_complete():
    from strategy.positioning.refresh_shadow import compare_captures

    url = "https://fixture.example.test/prices"
    capture = {"representation": "test", "complete": True,
               "pages": {url: "a" * 64, "https://fixture.example.test/terms": "invalid"}}
    dependency = {"page_url": url, "before_quote": "Price 40 EUR"}
    assert compare_captures(capture, capture, [dependency])["decision"] == "UNKNOWN"


def test_scrape_route_persists_fingerprint_from_its_own_manifest(application, monkeypatch, tmp_path):
    from api.jobs import runner
    from api.routes import scrape
    from scraper.source_capture import source_capture as capture_manifest
    from test_profile_refresh_review import terminal
    from tests.test_merger import _rich_manifest

    client, headers, service, _, data, _ = application
    manifest = _rich_manifest()
    for page in manifest.pages:
        page.content_hash = "a" * 64
    expected_capture = capture_manifest(manifest)
    assert expected_capture["pages"]
    monkeypatch.setattr(scrape, "is_safe_public_url", lambda url: url == data["url"])
    monkeypatch.setattr(scrape, "has_llm", lambda: False)
    monkeypatch.setattr(runner, "scraper_scrape", lambda *args, **kwargs: (manifest, tmp_path))

    started = client.post("/api/scrape", headers=headers, json={"url": data["url"]})
    assert terminal(client, headers, started)["status"] == "done"
    actor = UUID(data["actor"])
    job = service.job_for_user(job_id=UUID(started.json()["job_id"]), user_id=actor)
    run = service.run_for_user(run_id=job.run_id, user_id=actor)
    assert run.output["source_capture"] == expected_capture
    assert str(run.input_profile_id) == brand_document(client, headers, data)["profile_snapshot_id"]
