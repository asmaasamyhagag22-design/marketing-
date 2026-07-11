"""U7 Telemetry logger — run_id + crash-safe JSONL per stage-call (D-7 skeleton).

Design constraints (INTERFACES.md D-7 + §N Day-1):
- `run_id` minted at pipeline entry (or adopted from the TELEMETRY_RUN_ID env var, so a
  parent process — the benchmark runner, the studio — can stitch subprocess stages into
  ONE run record).
- One JSONL line per stage-call: {run_id, stage, ts, latency_ms, input_hash, output_hash,
  model, tokens_in, tokens_out, cost_usd, decision, status, note}. Missing fields are
  omitted, never invented.
- Crash-safe append: open-append + flush + fsync per line — a mid-run crash keeps every
  line already written (the record is the evidence of what DID happen).
- SHA-256 payload fingerprinting lives HERE (D-3 moved all hashing language to telemetry).
- PURE stdlib; never raises into the pipeline (telemetry must not break production).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_ENV_RUN_ID = "TELEMETRY_RUN_ID"
_ENV_ROOT = "TELEMETRY_ROOT"


def payload_hash(obj: Any) -> str:
    """SHA-256 fingerprint of any payload (canonical JSON for dicts/lists, utf-8 for str,
    raw for bytes). Stable across runs — the reproducibility key of a stage-call."""
    if obj is None:
        return ""
    if isinstance(obj, bytes):
        data = obj
    elif isinstance(obj, str):
        data = obj.encode("utf-8")
    else:
        try:
            data = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        except Exception:  # noqa: BLE001
            data = repr(obj).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class RunTelemetry:
    """One pipeline run's JSONL recorder. `runs/<run_id>/telemetry.jsonl`.

    Mint at the pipeline entry; pass down (or let children adopt via TELEMETRY_RUN_ID).
    Every public method is best-effort: telemetry must never break the pipeline."""

    def __init__(self, run_id: Optional[str] = None, root: Optional[str] = None):
        self.run_id = (run_id or os.environ.get(_ENV_RUN_ID)
                       or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_")
                       + uuid.uuid4().hex[:8])
        self.root = Path(root or os.environ.get(_ENV_ROOT) or "runs")
        self.path = self.root / self.run_id / "telemetry.jsonl"
        self._ready = False

    def _ensure(self) -> bool:
        if self._ready:
            return True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._ready = True
        except Exception:  # noqa: BLE001
            self._ready = False
        return self._ready

    def record(self, stage: str, *, status: str = "ok", latency_ms: Optional[float] = None,
               model: Optional[str] = None, tokens_in: Optional[int] = None,
               tokens_out: Optional[int] = None, cost_usd: Optional[float] = None,
               decision: Optional[str] = None, input_obj: Any = None, output_obj: Any = None,
               note: str = "") -> None:
        """Append ONE stage-call line (crash-safe). Fields not known are omitted."""
        if not self._ensure():
            return
        row: dict = {"run_id": self.run_id, "stage": stage,
                     "ts": datetime.now(timezone.utc).isoformat(), "status": status}
        if latency_ms is not None:
            row["latency_ms"] = round(float(latency_ms), 1)
        if input_obj is not None:
            row["input_hash"] = payload_hash(input_obj)
        if output_obj is not None:
            row["output_hash"] = payload_hash(output_obj)
        if model:
            row["model"] = model
        if tokens_in is not None:
            row["tokens_in"] = int(tokens_in)
        if tokens_out is not None:
            row["tokens_out"] = int(tokens_out)
        if cost_usd is not None:
            row["cost_usd"] = round(float(cost_usd), 6)
        if decision:
            row["decision"] = decision
        if note:
            row["note"] = note[:500]
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception:  # noqa: BLE001 — telemetry never breaks the pipeline
            pass

    @contextmanager
    def stage(self, name: str, *, input_obj: Any = None, **fields):
        """Time a stage block and record it (status=ok / error with the exception name).
        Yields a dict the block may fill with output_obj/model/cost_usd/... overrides."""
        extra: dict = {}
        t0 = time.monotonic()
        try:
            yield extra
        except Exception as e:  # noqa: BLE001
            self.record(name, status="error", latency_ms=(time.monotonic() - t0) * 1000,
                        input_obj=input_obj, note=f"{type(e).__name__}: {e}", **fields)
            raise
        merged = {**fields, **extra}
        self.record(name, status=merged.pop("status", "ok"),
                    latency_ms=(time.monotonic() - t0) * 1000,
                    input_obj=input_obj, **merged)

    def export_env(self) -> dict:
        """Env vars that let a CHILD PROCESS append to this same run record."""
        return {_ENV_RUN_ID: self.run_id, _ENV_ROOT: str(self.root)}
