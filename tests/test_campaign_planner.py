"""Campaign planner behavior through the authenticated application boundary."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest

from strategy.campaign_planner import anchored_claim
from strategy.campaign_research import Page
from test_app_review_graph import application
from test_review_workflow import database


BASE = "/api/v2/campaigns"
ROOT = "https://planned.example.test/"
QUOTE = "This feature blocks known trackers while you browse the web."


@pytest.fixture
def planner(application):
    from api.routes.v2_campaigns import get_package_loader

    client, headers, _, _, _, app = application
    root = f"https://planned-{uuid4().hex[:12]}.example.test/"
    feature = root + "tracker-protection"
    control = {"calls": [], "hook": None, "root": root, "feature": feature}
    pages = {
        root: '<h1>Example</h1><a href="/tracker-protection">Tracker protection</a>',
        feature: f"<h1>Tracker protection</h1><p>{QUOTE}</p>",
    }

    def load(url, timeout):
        control["calls"].append(url)
        if control["hook"]:
            control["hook"](url)
        if url not in pages:
            raise OSError("unavailable fixture source")
        body = f"<html><body><main>{pages[url]}</main></body></html>".encode()
        return Page(url, body, "synthetic_fault_fixture")

    app.dependency_overrides[get_package_loader] = lambda: load

    def request(method, path, body=None):
        if body and body.get("url") == ROOT:
            body = {**body, "url": root}
        return client.request(method, BASE + path, headers=headers, json=body)

    yield request, control, pages
    del app.dependency_overrides[get_package_loader]


def input_body(url=ROOT, objective="Increase visits to the tracker protection explanation", expected=None):
    return {"url": url, "objective": objective, "language": "en",
            "request_id": str(uuid4()), "expected_run_id": expected}


def edit(request, draft, **updates):
    body = {"run_id": draft["run_id"], "audience": "Reviewers interested in tracking protection.",
            "tone": "Concise and calm", "selected": draft["proposal"]["brief"]["selected"], **updates}
    return request("POST", f"/{draft['domain_key']}/brief", body)


def test_start_without_profile_is_versioned_replay_safe_and_blocks_claim_expansion(planner):
    request, control, _ = planner
    body = input_body()
    response = request("POST", "/plan", body)
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["reason"] == "BRIEF_REVIEW_REQUIRED" and not draft["proposal"]["package"]
    assert draft["proposal"]["evidence"][0]["quote"] == QUOTE
    assert draft["proposal"]["planner"]["trace"][0]["gap_after"] == "FEATURE_EVIDENCE"
    assert draft["proposal"]["planner"]["trace"][1]["gap_after"] is None
    assert request("POST", "/plan", body).json()["run_id"] == draft["run_id"]
    assert control["calls"] == [control["root"], control["feature"]]
    prefix = "/" + draft["domain_key"]
    assert request("POST", prefix + "/review", {"run_id": draft["run_id"], "decision": "approved"}).status_code == 409
    assert anchored_claim(draft["proposal"], "brief.summary", QUOTE)
    assert not anchored_claim(draft["proposal"], "package.copy.message", "This feature blocks all trackers.")
    assert edit(request, draft, message="This feature blocks all trackers.").status_code == 422
    accepted = edit(request, draft).json()
    assert accepted["run_id"] != draft["run_id"] and accepted["proposal"]["status"] == "READY"
    assert accepted["proposal"]["evidence"] == draft["proposal"]["evidence"]
    assert request("POST", "/plan", {**body, "expected_run_id": accepted["run_id"]}).status_code == 409
    assert control["calls"] == [control["root"], control["feature"]]


def test_target_changes_action_or_preserves_missing_requirement(planner):
    request, control, pages = planner
    pages[control["root"]] += '<a href="/download/options/">Download options</a>'
    pages[control["root"] + "download/options/"] = '<h1>Download options</h1>'
    first = request("POST", "/plan", input_body()).json()
    second = request("POST", "/plan", input_body(
        objective="Increase downloads for people interested in tracker protection", expected=first["run_id"],
    )).json()
    assert first["proposal"]["planner"]["options"][0]["action"] == "READ_FEATURE"
    assert second["proposal"]["planner"]["gap"] == "ACTION_DESTINATION"
    assert second["proposal"]["evidence"]
    assert second["proposal"]["package"] is None


def test_source_refresh_invalidates_approved_package(planner):
    request, control, pages = planner
    draft = request("POST", "/plan", input_body()).json()
    ready = edit(request, draft).json()
    path = "/" + draft["domain_key"]
    assert request("POST", path + "/review", {"run_id": ready["run_id"], "decision": "approved"}).json()["approved"]
    pages[control["feature"]] = "<h1>Notice</h1><p>The publisher removed this page content.</p>"
    refreshed = request("POST", path + "/refresh", {"run_id": ready["run_id"]}).json()
    assert refreshed["run_id"] != ready["run_id"] and refreshed["reason"] == "EVIDENCE_GAP"
    assert request("GET", path + "/package/export?run_id=" + ready["run_id"]).status_code == 409


def test_late_research_cannot_replace_newer_campaign(planner):
    request, control, _ = planner
    draft = request("POST", "/plan", input_body()).json()
    entered, proceed = Event(), Event()

    def wait_at_source(url):
        if url == control["root"]:
            entered.set()
            assert proceed.wait(10)

    control["hook"] = wait_at_source
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(request, "POST", "/plan", input_body(expected=draft["run_id"]))
        assert entered.wait(10)
        try:
            newer = edit(request, draft)
            assert newer.status_code == 200, newer.text
        finally:
            proceed.set()
        response = pending.result(timeout=15)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "CAMPAIGN_CHANGED"
    assert request("GET", "/" + draft["domain_key"]).json()["run_id"] == newer.json()["run_id"]


def test_commercial_promise_abstains_with_specific_question(planner):
    request, _, _ = planner
    draft = request("POST", "/plan", input_body(objective="Promote a discount for tracker protection")).json()
    assert draft["reason"] == "EVIDENCE_GAP"
    assert draft["proposal"]["planner"]["gap"] == "COMMERCIAL_TERMS"
    assert "validity" in draft["proposal"]["planner"]["missing_question"]



def test_contradictory_feature_evidence_requires_review(planner):
    request, control, pages = planner
    pages[control["feature"]] += "<p>Tracker protection is no longer available in this product.</p>"
    response = request("POST", "/plan", input_body())
    assert response.status_code == 200, response.text
    result = response.json()["proposal"]
    assert result["status"] == "BLOCKED" and result["planner"]["gap"] == "SOURCE_CONFLICT"
    assert result["planner"]["conflicts"][0]["page_url"] == control["feature"]
