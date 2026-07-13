# -*- coding: utf-8 -*-
"""scraper.fetcher retry policy — 429/5xx are transient (retried), hard 4xx are not.

Regression origin (MEASURED): bobana-eg.com returned HTTP 429 (Too-Many-Requests) on one
burst and the WHOLE scrape failed in 19s with 0 pages, surfacing "could not read this site".
A 429 means "slow down and retry", not "this site is unreadable" — the same URL served 200
moments later. These tests script _fetch_page_once's return values (hermetic — no Playwright,
no network) and assert the retry loop's decisions and its backoff.
"""
from __future__ import annotations

import scraper.fetcher as fetcher
from scraper.errors import ErrorCode
from scraper.fetcher import FetchResult
from scraper.time_utils import utc_now


def _result(status, error_code, retry_after=None):
    return FetchResult(url="u", final_url="u", http_status=status,
                       fetched_at=utc_now(), duration_ms=1,
                       error_code=error_code, retry_after_s=retry_after,
                       rendered_text=("ok" if error_code is None else ""))


def _script(monkeypatch, results):
    """Make _fetch_page_once pop from `results`; record call count + every sleep."""
    seq = list(results)
    calls = {"n": 0}
    sleeps: list[float] = []

    def fake_once(context, url, keep_page=False, light=False):
        calls["n"] += 1
        return seq.pop(0)

    monkeypatch.setattr(fetcher, "_fetch_page_once", fake_once)
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: sleeps.append(s))
    return calls, sleeps


def test_429_is_retried_then_succeeds(monkeypatch):
    calls, sleeps = _script(monkeypatch, [
        _result(429, ErrorCode.HTTP_ERROR),
        _result(200, None),
    ])
    r = fetcher.fetch_page(object(), "https://x")
    assert r.ok and r.http_status == 200
    assert calls["n"] == 2                                   # one retry consumed
    assert sleeps and sleeps[0] >= fetcher._RATE_LIMIT_BACKOFF_S   # slow backoff for a 429


def test_429_retry_after_header_honored_but_capped(monkeypatch):
    _calls, sleeps = _script(monkeypatch, [
        _result(429, ErrorCode.HTTP_ERROR, retry_after=999),   # absurd server ask -> capped
        _result(200, None),
    ])
    r = fetcher.fetch_page(object(), "https://x")
    assert r.ok
    assert sleeps[0] == fetcher._RETRY_AFTER_CAP_S             # honored, but a run can't stall


def test_5xx_is_retried(monkeypatch):
    calls, _ = _script(monkeypatch, [
        _result(503, ErrorCode.HTTP_ERROR),
        _result(200, None),
    ])
    r = fetcher.fetch_page(object(), "https://x")
    assert r.ok and calls["n"] == 2


def test_hard_4xx_not_retried(monkeypatch):
    calls, _ = _script(monkeypatch, [
        _result(404, ErrorCode.HTTP_ERROR),
        _result(200, None),          # would succeed IF retried — must NOT be reached
    ])
    r = fetcher.fetch_page(object(), "https://x")
    assert not r.ok and r.http_status == 404
    assert calls["n"] == 1           # a 404 won't fix itself -> no retry, no hammering


def test_429_exhausts_retries_then_fails_honestly(monkeypatch):
    calls, _ = _script(monkeypatch, [
        _result(429, ErrorCode.HTTP_ERROR),
        _result(429, ErrorCode.HTTP_ERROR),
        _result(429, ErrorCode.HTTP_ERROR),
    ])
    r = fetcher.fetch_page(object(), "https://x")
    assert not r.ok and r.http_status == 429                 # persistent 429 still fails honestly
    assert calls["n"] == 1 + fetcher.RETRY_ATTEMPTS          # first attempt + all retries
