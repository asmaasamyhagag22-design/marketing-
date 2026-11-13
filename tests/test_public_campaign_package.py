"""Isolated faults on the campaign HTTP and compositor boundaries."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from strategy.campaign_package import Brief, Source, capture
from strategy.campaign_research import Page
from test_app_review_graph import application
from test_review_workflow import database


CASE = Path(__file__).resolve().parents[1] / "docs/campaigns/firefox/brief.json"


@pytest.fixture
def campaign(application):
    from api.routes.v2_campaigns import get_clock, get_package_loader

    client, headers, service, _, data, app = application
    spec = Brief.model_validate_json(CASE.read_text()).model_dump(mode="json")
    spec["source"]["url"] = data["url"] + "/feature"
    spec["peer_source"]["url"] = "https://peer.example.test/feature"
    control = {"calls": [], "time": datetime.now(timezone.utc)}
    pages = {src["url"]: f"<html><body><p>{src['quote']}</p></body></html>".encode()
             for src in (spec["source"], spec["peer_source"])}

    def load(url, timeout):
        control["calls"].append(url)
        if url not in pages:
            raise OSError("Simulated timeout")
        return Page(url, pages[url], "synthetic_fault_fixture")

    app.dependency_overrides[get_package_loader] = lambda: load
    app.dependency_overrides[get_clock] = lambda: lambda: control["time"]
    path = "/api/v2/campaigns/" + data["domain"]

    def request(method, suffix="", body=None, auth=None):
        return client.request(method, path + suffix, json=body, headers=headers if auth is None else auth)

    yield request, spec, pages, control, service
    del app.dependency_overrides[get_package_loader]
    del app.dependency_overrides[get_clock]


def create(request, spec, expected=None):
    response = request("POST", "/package", {"brief": spec, "expected_run_id": expected})
    assert response.status_code == 200, response.text
    return response.json()


def approve(request, view):
    return request("POST", "/review", {"run_id": view["run_id"], "decision": "approved"})


@pytest.mark.parametrize("failure", ["source_changed", "source_unavailable"])
def test_evidence_change_hides_prior_export_and_requires_fresh_approval(campaign, failure):
    request, spec, pages, control, _ = campaign
    first = create(request, spec)
    assert approve(request, first).json()["approved"]
    prior = "/package/export?run_id=" + first["run_id"]
    before = len(control["calls"])
    replay = request("POST", "/package", {"brief": spec, "expected_run_id": None})
    assert replay.status_code == 409 and len(control["calls"]) == before
    source = spec["source"]["url"]
    if failure == "source_changed":
        pages[source] = b"<html><body><p>The publisher revised the feature.</p></body></html>"
    else:
        pages.pop(source)
    revised = request("POST", "/refresh", {"run_id": first["run_id"]}).json()
    assert revised["run_id"] != first["run_id"] and revised["reason"] == "EVIDENCE_GAP"
    assert revised["proposal"]["package"] is None
    assert not revised["approved"]
    assert revised["proposal"]["evidence"][0]["outcome"] == (
        "SOURCE_UNAVAILABLE" if failure == "source_unavailable" else "QUOTE_NOT_FOUND"
    )
    assert request("GET", prior).status_code == 409
    assert approve(request, revised).status_code == 409


def test_expiry_and_concurrent_approval_invalidate_export(campaign, monkeypatch):
    from poster import campaign_package

    request, spec, _, control, _ = campaign
    first = create(request, spec)
    assert approve(request, first).json()["approved"]

    def reject_during_render(view, root):
        reject = request("POST", "/review", {"run_id": view["run_id"], "decision": "rejected"})
        assert reject.status_code == 200 and not reject.json()["approved"]
        return b"should never be delivered"

    monkeypatch.setattr(campaign_package, "export_package", reject_during_render)
    path = "/package/export?run_id=" + first["run_id"]
    blocked = request("GET", path)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "CURRENT_PACKAGE_APPROVAL_REQUIRED"
    assert approve(request, first).json()["approved"]

    def reapprove_during_render(view, root):
        reject_during_render(view, root)
        assert approve(request, first).json()["approval_id"] != view["approval_id"]
        return b"should never be delivered"

    monkeypatch.setattr(campaign_package, "export_package", reapprove_during_render)
    blocked = request("GET", path)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "CURRENT_PACKAGE_APPROVAL_REQUIRED"
    control["time"] += timedelta(days=7)
    assert request("GET").json()["reason"] == "SOURCE_RECHECK_REQUIRED"
    assert approve(request, first).status_code == 409
    refreshed = request("POST", "/refresh", {"run_id": first["run_id"]}).json()
    assert refreshed["run_id"] != first["run_id"] and not refreshed["approved"]
    assert approve(request, refreshed).json()["approved"]


def test_foreign_owner_cannot_fetch_sources_or_render(campaign):
    from api.user_auth import issue_token

    request, spec, _, control, service = campaign
    first = create(request, spec)
    user = service.create_user(email=f"{uuid4().hex}@synthetic.invalid", hashed_password="disabled")
    headers = {"Authorization": "Bearer " + issue_token(str(user.id))}
    before = len(control["calls"])
    assert request("POST", "/package", {"brief": spec, "expected_run_id": first["run_id"]}, headers).status_code == 404
    assert request("GET", "/package/preview?size=square&run_id=" + first["run_id"], auth=headers).status_code == 404
    assert request("GET", "/package/export?run_id=" + first["run_id"], auth=headers).status_code == 404
    assert len(control["calls"]) == before


def test_hidden_and_ambiguous_quotes_are_rejected():
    source = Source(url="https://example.test/", quote="Free today", scope="Current offer scope")
    for html, expected in [
        ('<p style="display: none !important">Free today</p>', "QUOTE_NOT_FOUND"),
        ('<section hidden><p>Free today</p></section>', "QUOTE_NOT_FOUND"),
        ('<p>Free today</p><p>Free today for subscribers</p>', "QUOTE_CONTEXT_AMBIGUOUS"),
        ('<p style="color:red">Free today</p>', "QUOTE_OBSERVED"),
    ]:
        got = capture(source, lambda url, _: Page(url, html.encode()), lambda: datetime.now(timezone.utc))
        assert got["outcome"] == expected


def test_unusually_wide_copy_renders_at_square_size(tmp_path):
    import subprocess
    import sys

    # The broader suite installs a Playwright stub during collection. Use Chromium in a fresh process.
    script = """
from pathlib import Path
import sys
from poster.campaign_package import render_poster
from strategy.campaign_package import Brief, compile_package

brief = Brief.model_validate_json(Path(sys.argv[1]).read_text())
package = compile_package(brief, "Renderer Fixture", [{"page_url": brief.source.url}])
package["copy"] = {"headline": "W" * 55, "message": "W" * 105, "cta": "W" * 30}
package["direction"] = "ltr"
image, report = render_poster(package, "square", Path(sys.argv[2]) / "square.png")
assert image.startswith(bytes.fromhex("89504e470d0a1a0a"))
assert report["geometry"][-1]["bottom"] <= 1020
"""
    subprocess.run([sys.executable, "-c", script, str(CASE), str(tmp_path)], check=True,
                   cwd=CASE.parents[3], timeout=20)


def test_comparison_frames_fit_the_short_square_motif(tmp_path):
    import subprocess
    import sys

    script = """
from pathlib import Path
import sys
from poster.campaign_package import render_poster

package = {
    "brand_name": "Museum", "language": "en", "direction": "ltr",
    "theme": "cobalt", "poster_layout": "source-campaign@2", "concept": "compare",
    "copy": {"headline": "Compare Artworks Side by Side",
             "message": "Use the Comparator to place artworks next to each other and zoom in on the smallest details.",
             "cta": "Read about the Comparator"},
}
for size in ("square", "portrait"):
    image, measurements = render_poster(package, size, Path(sys.argv[1]) / (size + ".png"))
    motif = next(box for box in measurements["geometry"] if box["field"] == "motif")
    assert image.startswith(bytes.fromhex("89504e470d0a1a0a"))
    assert not motif["overflow"]
"""
    subprocess.run([sys.executable, "-c", script, str(tmp_path)], check=True,
                   cwd=CASE.parents[3], timeout=25)


def test_cached_bytes_survive_renderer_change_and_detect_corruption(monkeypatch, tmp_path):
    from poster import campaign_package

    run_id = str(uuid4())
    proposal_sha = "c" * 64
    view = {"run_id": run_id, "proposal": {"sha256": proposal_sha, "package": {}}}
    calls = []

    def fake_render(package, size, path):
        from hashlib import sha256
        calls.append(size)
        return b"first-render", {"sha256": sha256(b"first-render").hexdigest()}

    monkeypatch.setattr(campaign_package, "render_poster", fake_render)
    assert campaign_package.preview_poster(view, "square", tmp_path) == b"first-render"
    assert campaign_package.preview_poster(view, "square", tmp_path) == b"first-render"
    assert calls == ["square"]
    view.update(approval_id=str(uuid4()), profile_snapshot_id=str(uuid4()))
    first_archive = campaign_package.export_package(view, tmp_path)
    assert campaign_package.export_package(view, tmp_path) == first_archive
    assert calls == ["square", "portrait"]
    (tmp_path / run_id / proposal_sha / "square.zip").write_bytes(b"invalid")
    with pytest.raises(campaign_package.PosterLayoutError, match="POSTER_ARTIFACT_CORRUPT"):
        campaign_package.preview_poster(view, "square", tmp_path)
    assert calls == ["square", "portrait"]
