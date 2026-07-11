"""U7 Telemetry skeleton (telemetry/logger.py + the build_profile retrofit) — D-7.

Pins the Day-1 contract: run_id minted or adopted from env, one crash-safe JSONL line per
stage-call with SHA-256 payload hashes, the stage() context manager records ok AND error
paths, and a hermetic MockCaller build_profile produces a complete per-stage record
including the LLM stage's cost. Hermetic — no network (TELEMETRY_ROOT is tmp'd in conftest).
"""
from __future__ import annotations

import json
import os

from telemetry import RunTelemetry, payload_hash


def _lines(t: RunTelemetry) -> list[dict]:
    return [json.loads(l) for l in t.path.read_text(encoding="utf-8").splitlines()]


def test_payload_hash_stable_and_type_aware():
    assert payload_hash({"b": 1, "a": 2}) == payload_hash({"a": 2, "b": 1})   # canonical
    assert payload_hash("x") != payload_hash("y")
    assert payload_hash(None) == ""


def test_record_writes_one_crash_safe_line_per_call(tmp_path):
    t = RunTelemetry(root=str(tmp_path))
    t.record("rules", latency_ms=12.34, input_obj={"m": 1}, output_obj="ok-hash-src")
    t.record("llm_extraction", model="gemini-2.5-flash", tokens_in=100, tokens_out=50,
             cost_usd=0.0014, note="4/4 calls ok")
    rows = _lines(t)
    assert [r["stage"] for r in rows] == ["rules", "llm_extraction"]
    assert rows[0]["run_id"] == t.run_id and rows[0]["status"] == "ok"
    assert rows[0]["input_hash"] == payload_hash({"m": 1})
    assert rows[1]["cost_usd"] == 0.0014 and rows[1]["model"] == "gemini-2.5-flash"


def test_stage_context_times_and_records_errors(tmp_path):
    t = RunTelemetry(root=str(tmp_path))
    with t.stage("merge") as x:
        x["decision"] = "ready"
    try:
        with t.stage("validate"):
            raise ValueError("boom")
    except ValueError:
        pass
    rows = _lines(t)
    assert rows[0]["stage"] == "merge" and rows[0]["decision"] == "ready"
    assert rows[0]["latency_ms"] >= 0
    assert rows[1]["stage"] == "validate" and rows[1]["status"] == "error"
    assert "ValueError" in rows[1]["note"]


def test_child_process_adopts_run_id_via_env(tmp_path, monkeypatch):
    parent = RunTelemetry(root=str(tmp_path))
    for k, v in parent.export_env().items():
        monkeypatch.setenv(k, v)
    child = RunTelemetry()                      # adopts run_id + root from env
    child.record("subprocess_stage")
    assert child.run_id == parent.run_id and child.path == parent.path


def test_build_profile_emits_a_complete_stage_record(tmp_path, monkeypatch):
    # The D-7 GATE shape, hermetically: a MockCaller build produces one telemetry.jsonl
    # with rules -> evidence_pack -> llm_extraction (incl. cost) -> validate -> merge.
    monkeypatch.setenv("TELEMETRY_ROOT", str(tmp_path / "runs"))
    import glob

    from business_profile.build import build_profile
    from business_profile.llm.caller import MockCaller
    from tests.test_merger import _full_staged_responses, _rich_manifest

    build_profile(_rich_manifest(), MockCaller(_full_staged_responses()))
    files = glob.glob(str(tmp_path / "runs" / "*" / "telemetry.jsonl"))
    assert len(files) == 1
    rows = [json.loads(l) for l in open(files[0], encoding="utf-8")]
    stages = [r["stage"] for r in rows]
    assert stages == ["rules", "evidence_pack", "llm_extraction", "validate", "merge"]
    llm = rows[2]
    assert "cost_usd" in llm and "latency_ms" in llm            # the gate: cost is recorded
    assert rows[4]["decision"] in ("ready", "not_ready")
    assert len({r["run_id"] for r in rows}) == 1                # one run record
