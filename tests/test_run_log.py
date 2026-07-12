# -*- coding: utf-8 -*-
"""Human-readable run logs (Phase 0 — logs as a product) — hermetic.

Pins: plain bilingual step lines rendered from the EXISTING telemetry JSONL (no new
instrumentation), the per-run cost summary the dashboard surfaces, the INDEX row, and the
graceful-empty contract on a missing run."""
from __future__ import annotations

import json

from telemetry import run_log


def _write_run(root, run_id, rows):
    d = root / run_id
    d.mkdir(parents=True)
    (d / "telemetry.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


def test_render_run_log_is_plain_bilingual(tmp_path):
    rows = [
        {"run_id": "r1", "stage": "scrape", "status": "ok", "ts": "2026-07-12T09:00:01+00:00",
         "latency_ms": 4200},
        {"run_id": "r1", "stage": "media_plan", "status": "ok", "ts": "2026-07-12T09:05:00+00:00",
         "model": "gemini-2.5-pro", "tokens_in": 1000, "tokens_out": 200, "cost_usd": 0.012},
        {"run_id": "r1", "stage": "reel", "status": "error", "ts": "2026-07-12T09:20:00+00:00",
         "note": "quota 429"},
    ]
    _write_run(tmp_path / "runs", "r1", rows)
    p = run_log.render_run_log("r1", "nti", runs_dir=str(tmp_path / "runs"),
                               logs_dir=str(tmp_path / "logs"))
    text = p.read_text(encoding="utf-8")
    assert "قراءة موقع البراند" in text and "Reading the brand's website" in text
    assert "بناء خطة الشراء الإعلاني" in text and "Building the media plan" in text
    assert "⚠" in text and "quota 429" in text        # the failure is RELOCATED here, not hidden
    assert "~$0.0120" in text                          # cost surfaced
    # no raw JSON keys / dev jargon leaked into the human log
    assert "latency_ms" not in text and "tokens_in" not in text


def test_run_cost_aggregates(tmp_path):
    rows = [
        {"stage": "a", "model": "m", "cost_usd": 0.01, "tokens_in": 100, "tokens_out": 50,
         "latency_ms": 1000},
        {"stage": "b", "model": "m", "cost_usd": 0.02, "tokens_in": 200, "tokens_out": 80,
         "latency_ms": 2000},
        {"stage": "c", "status": "error", "latency_ms": 500},
    ]
    _write_run(tmp_path / "runs", "r2", rows)
    c = run_log.run_cost("r2", runs_dir=str(tmp_path / "runs"))
    assert c["cost_usd"] == 0.03 and c["llm_calls"] == 2 and c["stages"] == 3
    assert c["tokens_in"] == 300 and c["errors"] == 1


def test_index_upsert_is_idempotent(tmp_path):
    logs = tmp_path / "logs"
    run_log.update_index("r1", "nti", date="2026-07-12", outcome="✓ done", logs_dir=str(logs))
    run_log.update_index("r1", "nti", date="2026-07-12", outcome="✓ redone", logs_dir=str(logs))
    text = (logs / "INDEX.md").read_text(encoding="utf-8")
    assert text.count("| r1 | nti |") == 1            # refreshed, not duplicated
    assert "redone" in text and "nti.log" in text


def test_missing_run_degrades_gracefully(tmp_path):
    assert run_log.render_run_log("nope", "x", runs_dir=str(tmp_path), logs_dir=str(tmp_path)) is None
    assert run_log.run_cost("nope", runs_dir=str(tmp_path))["cost_usd"] == 0.0
    assert run_log.read_run("nope", runs_dir=str(tmp_path)) == []
