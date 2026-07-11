"""Shared test fixtures.

U7 telemetry writes runs/<run_id>/telemetry.jsonl per pipeline run; tests must not
pollute the repo root, so every test gets an isolated TELEMETRY_ROOT under tmp.
"""
import pytest


@pytest.fixture(autouse=True)
def _telemetry_tmp_root(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEMETRY_ROOT", str(tmp_path / "telemetry_runs"))
    monkeypatch.delenv("TELEMETRY_RUN_ID", raising=False)
