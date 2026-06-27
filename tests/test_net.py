"""scraper.net — resilient HTTP fetch: bounded retry + per-host circuit breaker.

Hermetic: urllib.request.urlopen is monkeypatched, time.sleep/monotonic faked — no
network, no real waiting. Pins the robustness contract adopted from the competitor
repo's base_scraper.
"""
from __future__ import annotations

import scraper.net as net


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _no_sleep(monkeypatch):
    monkeypatch.setattr(net.time, "sleep", lambda *_a, **_k: None)


def test_success_returns_and_resets_circuit(monkeypatch):
    net.reset_circuits()
    monkeypatch.setattr(net.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResp(b'{"a": 1}'))
    assert net.get_json("https://h.example/x") == {"a": 1}
    assert not net.circuit_is_open("h.example")


def test_transient_failure_is_retried_then_returns_none(monkeypatch):
    net.reset_circuits()
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def _open(req, timeout=None):
        calls["n"] += 1
        raise net.urllib.error.URLError("boom")

    monkeypatch.setattr(net.urllib.request, "urlopen", _open)
    assert net.get_json("https://h.example/x", retries=2) is None
    assert calls["n"] == 3                      # 1 initial + 2 retries


def test_404_is_not_retried(monkeypatch):
    net.reset_circuits()
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def _open(req, timeout=None):
        calls["n"] += 1
        raise net.urllib.error.HTTPError("u", 404, "nf", None, None)

    monkeypatch.setattr(net.urllib.request, "urlopen", _open)
    assert net.get_json("https://h.example/x", retries=2) is None
    assert calls["n"] == 1                       # a clean 4xx won't fix itself


def test_503_is_retried(monkeypatch):
    net.reset_circuits()
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def _open(req, timeout=None):
        calls["n"] += 1
        raise net.urllib.error.HTTPError("u", 503, "busy", None, None)

    monkeypatch.setattr(net.urllib.request, "urlopen", _open)
    assert net.get_json("https://h.example/x", retries=2) is None
    assert calls["n"] == 3                       # transient status -> retried


def test_circuit_opens_after_threshold_and_short_circuits(monkeypatch):
    net.reset_circuits()
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def _open(req, timeout=None):
        calls["n"] += 1
        raise net.urllib.error.URLError("down")

    monkeypatch.setattr(net.urllib.request, "urlopen", _open)
    # Each call (retries=0) is one failure; after _FAILURE_LIMIT the circuit opens.
    for _ in range(net._FAILURE_LIMIT):
        assert net.get_json("https://dead.example/x", retries=0) is None
    hit = calls["n"]
    assert net.circuit_is_open("dead.example")
    # Subsequent calls short-circuit — the network is NOT touched.
    assert net.get_json("https://dead.example/x", retries=0) is None
    assert calls["n"] == hit


def test_circuit_half_opens_after_cooldown(monkeypatch):
    net.reset_circuits()
    clock = {"now": 1000.0}
    monkeypatch.setattr(net.time, "monotonic", lambda: clock["now"])
    for _ in range(net._FAILURE_LIMIT):
        net._record_fail("h.example")
    assert net.circuit_is_open("h.example")
    clock["now"] += net._COOLDOWN_S + 1.0
    assert not net.circuit_is_open("h.example")  # a probe is allowed again
