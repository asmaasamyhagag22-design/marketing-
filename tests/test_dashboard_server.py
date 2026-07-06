"""The LOCAL interactive studio (dashboard/server.py): SSE framing, slug guard, the landing page,
and the full analyze -> studio -> generate -> asset flow over a real socket with the pipeline FAKED
(hermetic - no network, no LLM, no Veo).

Origin: owner wants to sit IN the dashboard and DRIVE it — analyze fast, then press "Generate
poster" / "Generate reel" on demand and regenerate. This locks the wiring without ever running the
real (paid) generation.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from dashboard import server as srv


def test_sse_frames_are_well_formed():
    frame = srv.sse("stage", {"msg": "line\nwith newline"}).decode("utf-8")
    assert frame.startswith("event: stage\n") and frame.endswith("\n\n")
    body = frame.split("data: ", 1)[1].rstrip("\n")
    assert json.loads(body)["msg"] == "line\nwith newline"


def test_slug_guard_rejects_traversal():
    assert srv._ok_slug("brand_example")
    assert not srv._ok_slug("../secret")
    assert not srv._ok_slug("a/b")
    assert not srv._ok_slug("")


def test_landing_page_wires_analyze_over_sse():
    html = srv._landing_html()
    assert 'id="url"' in html and 'id="go"' in html                 # URL box + Analyze
    assert "Baseera" in html and "#B85C7A" in html                  # brand + blush palette
    assert "/analyze?url=" in html and "EventSource" in html        # SSE to analyze
    assert "/studio?slug=" in html                                  # then hands off to the studio


@pytest.fixture()
def live(tmp_path, monkeypatch):
    """A real server on an ephemeral port with analyze/generate FAKED (no network/LLM/Veo)."""
    def fake_analyze(url, *, out_dir="outputs", on_progress=None):
        on_progress("stage_start", "Scrape + Profile + Competitors + SWOT", "  -> Scrape ...")
        on_progress("stage_ok", "Scrape + Profile + Competitors + SWOT", "    [OK] Scrape  (1s)")
        slug = srv._run_mod._slug(url)
        P = srv._run_mod.paths(slug, out_dir)
        P["out"].mkdir(parents=True, exist_ok=True)
        P["result"].write_text(json.dumps({
            "subject_url": url, "subject_category": "ecommerce", "competitor_count": 0,
            "swot": {"mode": "standalone",
                     "strengths": [{"text": "Social links: 5", "citation": ["your scraped site"]}],
                     "weaknesses": [], "opportunities": [], "threats": []},
            "competitors": [], "tows": {},
            "profile": {"name": {"value": "Test Brand"}, "category": {"value": "ecommerce"}},
        }), encoding="utf-8")
        P["profile"].write_text(json.dumps(
            {"name": {"value": "Test Brand"}, "category": {"value": "ecommerce"}}), encoding="utf-8")
        return slug

    def fake_poster(slug, *, out_dir="outputs", on_progress=None):
        on_progress("stage_start", "Poster (one-shot)", "  -> Poster ...")
        P = srv._run_mod.paths(slug, out_dir)
        P["poster"].parent.mkdir(parents=True, exist_ok=True)
        P["poster"].write_bytes(b"\x89PNG\r\n\x1a\nFAKE-POSTER")
        on_progress("stage_ok", "Poster (one-shot)", "    [OK] Poster  (2s)")
        return P["poster"]

    monkeypatch.setattr("dashboard.run.analyze", fake_analyze)
    monkeypatch.setattr("dashboard.run.generate_poster", fake_poster)
    srv._Handler.out_dir = str(tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv._Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    _host, port = httpd.server_address
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(url: str, timeout: float = 10.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def test_analyze_streams_stages_then_slug(live):
    _s, body = _get(live + "/analyze?url=https://brand.example/")
    stream = body.decode("utf-8")
    assert "event: stage" in stream and "[OK] Scrape" in stream
    assert "event: done" in stream
    done = [l for l in stream.splitlines() if l.startswith("data:")][-1]
    assert json.loads(done[len("data: "):])["slug"] == "brand_example"


def test_studio_renders_report_plus_creative_studio(live):
    _get(live + "/analyze?url=https://brand.example/")                 # seed the artifacts
    _s, body = _get(live + "/studio?slug=brand_example")
    h = body.decode("utf-8")
    assert "Test Brand" in h                                           # the report renders
    assert "Creative Studio" in h                                      # the interactive block
    assert "gen('poster')" in h and "gen('reel')" in h                 # both generate buttons
    assert "Generate poster" in h and "Generate reel" in h            # empty -> "Generate"
    # the FAST poster auto-runs; the 10-20 min reel is opt-in so nobody lands on a 25-min wait
    assert "AUTO={poster:true,reel:false}" in h


def test_studio_does_not_rerun_existing_assets(live):
    _get(live + "/analyze?url=https://brand.example/")
    _get(live + "/generate/poster?slug=brand_example")                 # poster now exists (fake)
    _s, body = _get(live + "/studio?slug=brand_example")
    h = body.decode("utf-8")
    # poster exists -> don't auto-rerun it (shows Regenerate); reel is opt-in -> never auto-run
    assert "AUTO={poster:false,reel:false}" in h
    assert "Regenerate" in h


def test_generate_poster_then_serve_the_asset(live):
    _get(live + "/analyze?url=https://brand.example/")
    _s, body = _get(live + "/generate/poster?slug=brand_example")
    stream = body.decode("utf-8")
    assert "event: done" in stream and "/asset?slug=brand_example&kind=poster" in stream
    status, data = _get(live + "/asset?slug=brand_example&kind=poster")
    assert status == 200 and data.startswith(b"\x89PNG")


def test_bad_slug_and_missing_analysis_are_guarded(live):
    with pytest.raises(urllib.error.HTTPError) as e1:
        _get(live + "/studio?slug=../etc")
    assert e1.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as e2:
        _get(live + "/asset?slug=brand_example&kind=poster")           # never generated
    assert e2.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e3:
        _get(live + "/studio?slug=neveranalyzed")
    assert e3.value.code == 404
