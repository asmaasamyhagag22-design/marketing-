from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

import pytest

from strategy.campaign_research import Page
from test_app_review_graph import application
from test_profile_refresh_review import replace_profile
from test_review_workflow import database
from workflows.v2_cases import ENDS, NAME, NOW, home, offer_page


@pytest.fixture
def campaign(application):
    from api.routes.v2_campaigns import get_clock, get_page_loader

    client, headers, service, _, data, app = application
    control = {"now": NOW, "body": offer_page(), "calls": [], "on_offer": None}

    def load(url, timeout):
        control["calls"].append(url)
        path = urlsplit(url).path
        if path in {"", "/"}:
            return Page(url, home(["team", "terms"]))
        if control["on_offer"]:
            control["on_offer"]()
        return Page(url, control["body"])

    app.dependency_overrides[get_page_loader] = lambda: load
    app.dependency_overrides[get_clock] = lambda: lambda: datetime.fromisoformat(control["now"])
    yield client, headers, service, data, control
    del app.dependency_overrides[get_page_loader]
    del app.dependency_overrides[get_clock]


def post(campaign, suffix="", **body):
    client, headers, _, data, _ = campaign
    return client.post(f"/api/v2/campaigns/{data['domain']}{suffix}", json=body, headers=headers)


def start(campaign, previous=None):
    return post(campaign, goal="زيادة حجوزات التجربة", offer_name=NAME, expected_run_id=previous)


def status(campaign):
    client, headers, _, data, _ = campaign
    return client.get(f"/api/v2/campaigns/{data['domain']}", headers=headers).json()


def approve(campaign, run):
    return post(campaign, "/review", run_id=run, decision="approved")


def test_price_refresh_revises_exact_campaign_and_requires_another_approval(campaign):
    from sqlalchemy import select
    from db.models import RunDependency

    _, _, service, _, control = campaign
    initial = start(campaign)
    assert initial.status_code == 200, initial.text
    first = initial.json()
    assert first["proposal"]["research"]["page_calls"] == 2 and not first["approved"]
    assert first["proposal"]["creative"]["copy"]["price"] == "40 EUR"
    assert approve(campaign, first["run_id"]).json()["approved"] is True
    same = post(campaign, "/refresh", run_id=first["run_id"]).json()
    assert same["run_id"] == first["run_id"] and same["approved"]
    assert start(campaign).status_code == 409

    control["body"] = offer_page(price="55")
    changed = post(campaign, "/refresh", run_id=first["run_id"]).json()
    assert changed["run_id"] != first["run_id"] and not changed["approved"]
    assert changed["proposal"]["creative"]["copy"]["price"] == "55 EUR"
    impact, = changed["proposal"]["changes"]
    assert (impact["field"], impact["before"], impact["after"]) == ("price", "40", "55")
    assert approve(campaign, first["run_id"]).status_code == 409
    assert approve(campaign, changed["run_id"]).json()["approved"] is True
    with service._uow_factory() as uow:
        row = uow.session.scalar(select(RunDependency).where(
            RunDependency.run_id == UUID(changed["run_id"])))
        assert str(row.depends_on_run_id) == first["run_id"] and row.relation == "revises_campaign"


def test_new_exception_with_identical_offer_fields_blocks_draft(campaign):
    _, _, _, _, control = campaign
    first = start(campaign).json()
    assert approve(campaign, first["run_id"]).json()["approved"] is True
    qualifier = "لا يسري العرض في عطلة الأسبوع."
    control["body"] = offer_page(extra=f"<p>{qualifier}</p>")
    blocked = post(campaign, "/refresh", run_id=first["run_id"]).json()
    assert blocked["proposal"]["status"] == "BLOCKED"
    assert blocked["proposal"]["creative"] is None and not blocked["approved"]
    assert blocked["proposal"]["changes"][0]["observed_excerpt"] == qualifier
    assert approve(campaign, blocked["run_id"]).status_code == 409
    control["body"] = offer_page(terms=qualifier)
    repaired = post(campaign, "/refresh", run_id=blocked["run_id"]).json()
    assert repaired["proposal"]["creative"]["copy"]["terms"] == qualifier and not repaired["approved"]


def test_expiration_blocks_before_and_after_identical_capture(campaign):
    _, _, _, _, control = campaign
    first = start(campaign).json()
    assert approve(campaign, first["run_id"]).json()["approved"] is True
    control["now"] = ENDS
    expired = status(campaign)
    assert expired["reason"] == "OFFER_EXPIRED" and not expired["approved"]
    assert approve(campaign, first["run_id"]).status_code == 409
    refreshed = post(campaign, "/refresh", run_id=first["run_id"]).json()
    impact, = refreshed["proposal"]["changes"]
    assert impact["before_sha256"] == impact["after_sha256"]
    assert impact["after"] == "OFFER_EXPIRED" and refreshed["proposal"]["creative"] is None


def test_profile_change_while_researching_refuses_commit(campaign):
    _, _, service, data, control = campaign
    control["on_offer"] = lambda: replace_profile(service, data)
    response = start(campaign)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "PROFILE_CHANGED"
    assert status(campaign)["run_id"] is None


def test_non_owner_cannot_read_or_trigger_research(campaign):
    from api.user_auth import issue_token

    client, _, service, data, control = campaign
    other = service.create_user(email="other@synthetic.invalid", hashed_password="disabled")
    headers = {"Authorization": "Bearer " + issue_token(str(other.id))}
    path = f"/api/v2/campaigns/{data['domain']}"
    assert client.get(path, headers=headers).status_code == 404
    response = client.post(path, headers=headers, json={
        "expected_run_id": None, "goal": "زيادة حجوزات التجربة", "offer_name": NAME})
    assert response.status_code == 404 and not control["calls"]


def test_localized_copy_keeps_expiry_seconds_and_source_offset():
    from strategy.campaign_research import parse_offer
    from strategy.campaign_v2 import compile_copy

    expiry = "2026-12-01T09:23:45+05:30"
    offer = parse_offer(Page("https://studio.example.test/terms", offer_page(ends=expiry)),
                        NAME, datetime.fromisoformat(NOW))
    assert compile_copy(offer.as_dict())["validity"] == "2026-12-01 09:23:45 (UTC+05:30)"
