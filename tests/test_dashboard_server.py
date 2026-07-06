"""The LOCAL live app (dashboard/server.py): SSE framing, path-traversal guard, the landing page,
and a full run over a real socket with the pipeline FAKED (hermetic - no network, no LLM).

Origin: owner wants the dashboard as a local web app - "open it in the browser, paste a URL, watch
the process" - not a one-shot CLI. This locks the wiring: progress streams as SSE stage events and
the finished dashboard is served back, without ever running the real (paid) pipeline in tests.
"""
from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from dashboard import server as srv


def test_sse_frames_are_well_formed():
    frame = srv.sse("stage", {"msg": "line\nwith newline"}).decode("utf-8")
    assert frame.startswith("event: stage\n")
    assert frame.endswith("\n\n")
    # the payload is JSON, so an embedded newline can't break the single data: line
    body = frame.split("data: ", 1)[1].rstrip("\n")
    assert json.loads(body)["msg"] == "line\nwith newline"


def test_safe_out_file_blocks_traversal(tmp_path: Path):
    (tmp_path / "brand_dashboard.html").write_text("ok", encoding="utf-8")
    assert srv._safe_out_file(tmp_path, "brand_dashboard.html") is not None
    assert srv._safe_out_file(tmp_path, "../secret.html") is None
    assert srv._safe_out_file(tmp_path, "brand.txt") is None          # only .html
    assert srv._safe_out_file(tmp_path, "nope.html") is None          # must exist


def test_landing_page_has_the_input_and_baseera_identity():
    html = srv._landing_html()
    assert 'id="url"' in html and 'type="url"' in html               # the URL box
    assert 'id="go"' in html                                          # the Analyze button
    assert "Baseera" in html and "#B85C7A" in html                   # brand + blush palette
    assert "EventSource" in html and "/run?url=" in html             # live SSE wiring


@pytest.fixture()
def live_server(tmp_path, monkeypatch):
    """A real server on an ephemeral port with run_pipeline FAKED (no network/LLM)."""
    def fake_pipeline(url, *, fast=False, out_dir="outputs", open_when_done=False, on_progress=None):
        on_progress("stage_start", "Scrape + Profile + Competitors + SWOT", "  -> Scrape ...")
        on_progress("stage_ok", "Scrape + Profile + Competitors + SWOT", "    [OK] Scrape  (1s)")
        p = Path(out_dir) / "brand_dashboard.html"
        p.write_text("<html><body>DASH-OK</body></html>", encoding="utf-8")
        return p

    monkeypatch.setattr("dashboard.run.run_pipeline", fake_pipeline)
    srv._Handler.out_dir = Path(tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv._Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    host, port = httpd.server_address
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(url: str, timeout: float = 10.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")


def test_run_streams_stage_events_then_done(live_server):
    stream = _get(live_server + "/run?url=https://brand.com&fast=1")
    assert "event: stage" in stream                                  # progress streamed
    assert "[OK] Scrape" in stream
    assert "event: done" in stream                                   # finished
    # the done frame points at the served dashboard
    done = [l for l in stream.splitlines() if l.startswith("data:")][-1]
    view = json.loads(done[len("data: "):])["view"]
    assert view == "/view?f=brand_dashboard.html"
    # ...and that view actually serves the built dashboard
    assert "DASH-OK" in _get(live_server + view)


def test_run_rejects_a_non_url(live_server):
    stream = _get(live_server + "/run?url=not-a-url")
    assert "event: failed" in stream
    assert "http" in stream.lower()


def test_view_traversal_is_404(live_server):
    import urllib.error
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(live_server + "/view?f=../../etc/passwd.html")
    assert e.value.code == 404
