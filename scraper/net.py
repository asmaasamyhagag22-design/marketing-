"""Resilient HTTP fetch — bounded retry + a per-host CIRCUIT BREAKER.

Idea adopted from the competitor repo's `base_scraper` (circuit breaker + a tight
retry session + fast timeout), re-implemented stdlib-only (urllib) to match this
project's "no extra deps, NEVER raises" discipline for data-gathering helpers.

Why this matters: our keyless data-fetchers (trends sources, search providers, deep
search) make MANY GETs per run — HackerNews alone fans out one call per story. With
no circuit breaker, a dead/slow host gets hammered call after call, each paying the
full timeout, stalling the whole pipeline. Here, after a host fails N times in a row
the circuit OPENS and subsequent calls short-circuit to None instantly (no network),
until a cooldown lets one probe through (half-open). Transient failures (timeout /
connection / 429 / 5xx) are retried with linear backoff; a clean 4xx or a bad-JSON
200 is NOT retried (it won't fix itself).

Never raises: every failure path returns None.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

# Circuit-breaker tuning (mirrors the competitor repo: open after 3 consecutive fails).
_FAILURE_LIMIT = 3
_COOLDOWN_S = 60.0          # after opening, allow one probe again after this long
# Retried only on TRANSIENT failures.
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_DEFAULT_UA = "Mozilla/5.0 (compatible; MarketingScraper/0.1)"

# host -> (consecutive_failures, opened_at_monotonic). Module-level so the breaker
# spans all calls in a process (a long-lived API server included).
_state: dict[str, tuple[int, float]] = {}


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or url).lower()
    except Exception:
        return url


def circuit_is_open(key: str) -> bool:
    """True when `key` has failed >= _FAILURE_LIMIT in a row AND the cooldown has not
    yet elapsed (so we skip the network entirely). After the cooldown one probe is
    allowed (half-open); a success there resets the breaker."""
    fails, opened_at = _state.get(key, (0, 0.0))
    if fails < _FAILURE_LIMIT:
        return False
    return (time.monotonic() - opened_at) < _COOLDOWN_S


def _record_ok(key: str) -> None:
    _state.pop(key, None)


def _record_fail(key: str) -> None:
    fails, opened_at = _state.get(key, (0, 0.0))
    fails += 1
    # Stamp the open time exactly when we cross the threshold (start of the cooldown).
    if fails >= _FAILURE_LIMIT and opened_at == 0.0:
        opened_at = time.monotonic()
    elif fails >= _FAILURE_LIMIT:
        opened_at = time.monotonic()
    _state[key] = (fails, opened_at)


def reset_circuits() -> None:
    """Clear all breaker state (used by tests and between independent runs)."""
    _state.clear()


def get_json(
    url: str,
    *,
    key: Optional[str] = None,
    timeout: int = 8,
    retries: int = 2,
    backoff: float = 0.4,
    headers: Optional[dict] = None,
):
    """GET `url` and parse JSON. Returns the decoded object, or None on ANY failure /
    open circuit. `key` groups the breaker (defaults to the host) so all calls to one
    host share its failure state. Transient failures retry up to `retries` times."""
    ck = key or _host_of(url)
    if circuit_is_open(ck):
        return None

    hdrs = {"User-Agent": _DEFAULT_UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)

    return _request_json(url, ck, timeout, retries, backoff, hdrs, None)


def post_json(
    url: str,
    body: dict,
    *,
    key: Optional[str] = None,
    timeout: int = 12,
    retries: int = 2,
    backoff: float = 0.4,
    headers: Optional[dict] = None,
):
    """POST `body` as JSON and parse the JSON response — same bounded-retry + circuit
    breaker as get_json. Returns the decoded object, or None on failure / open circuit.
    Use `or {}` at the call site if you index the result directly."""
    ck = key or _host_of(url)
    if circuit_is_open(ck):
        return None
    hdrs = {"User-Agent": _DEFAULT_UA, "Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    try:
        payload = json.dumps(body).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return _request_json(url, ck, timeout, retries, backoff, hdrs, payload)


def _request_json(url, ck, timeout, retries, backoff, hdrs, payload):
    """Shared GET/POST retry loop. `payload` None -> GET, else POST. Never raises."""
    method = "POST" if payload is not None else "GET"
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=payload, headers=hdrs, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            _record_ok(ck)
            return data
        except urllib.error.HTTPError as e:
            # Retry only transient statuses; a 4xx won't fix itself.
            if e.code in _TRANSIENT_STATUS and attempt < retries:
                time.sleep(backoff * (attempt + 1))
                continue
            break
        except (urllib.error.URLError, TimeoutError, OSError):
            # Network / DNS / timeout — transient, worth a retry.
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
                continue
            break
        except (ValueError, json.JSONDecodeError):
            # A 2xx with unparseable body — not transient, don't retry.
            break
        except Exception:
            break

    _record_fail(ck)
    return None
