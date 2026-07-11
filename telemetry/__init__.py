"""U7 Telemetry (INTERFACES §F D-7) — the structured JSONL run-record layer.

One line per STAGE-CALL: {run_id, stage, ts, latency_ms, input_hash, output_hash,
model, tokens_in, tokens_out, cost_usd, decision, status, note}. Wraps the existing
aggregates (StageEvent, LLMExtractionResult.extraction_meta) — never replaces them.
SHA-256 payload fingerprinting lives HERE and nowhere else (D-3).
"""
from .logger import RunTelemetry, payload_hash

__all__ = ["RunTelemetry", "payload_hash"]
