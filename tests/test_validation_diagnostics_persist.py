"""Tests for ExtractionMeta.validation_diagnostics (2026-05).

Small fix: persist a structured summary of validator activity onto
extraction_meta so post-hoc questions like "what did the validator
reject?" can be answered from the saved profile JSON without re-running.

The structured form is intentionally a small summary (counts + truncated
quote strings), not the full per-rejection record list — keeps the
profile JSON compact.
"""
from __future__ import annotations

import sys
import types
from dataclasses import field
from datetime import datetime, timezone

_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for _n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, _n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from business_profile.llm.validator import (  # noqa: E402
    RejectionRecord, ValidationDiagnostics,
)
from business_profile.merger import _build_meta  # noqa: E402
from business_profile.schemas import ExtractionMeta  # noqa: E402


def _empty_base_meta() -> ExtractionMeta:
    return ExtractionMeta(
        manifest_path="x.json",
        extracted_at=datetime.now(timezone.utc),
    )


def test_empty_diagnostics_produces_zero_counts_structured():
    """When the validator had nothing to reject, the structured field
    must still be populated (with zero counts) — NOT None."""
    diag = ValidationDiagnostics()
    meta = _build_meta(_empty_base_meta(), llm_result=None, diagnostics=diag)
    assert meta.validation_diagnostics is not None
    assert meta.validation_diagnostics["total_rejections"] == 0
    assert meta.validation_diagnostics["fields_dropped"] == []
    assert meta.validation_diagnostics["items_dropped"] == {}


def test_diagnostics_records_rejections_by_group():
    """A real validator pass with rejections must surface the per-group
    counts in the persisted structure."""
    diag = ValidationDiagnostics()
    diag.rejections_by_group["identity"] = [
        RejectionRecord(code="block_not_found", block_id="b1", quote="some quote", note=""),
    ]
    diag.rejections_by_group["offerings"] = [
        RejectionRecord(code="quote_not_in_block", block_id="b2", quote="another quote", note=""),
        RejectionRecord(code="block_not_found", block_id="b3", quote="third", note=""),
    ]
    diag.items_dropped["offerings"] = 1
    diag.candidates_seen["offerings"] = 5

    meta = _build_meta(_empty_base_meta(), llm_result=None, diagnostics=diag)
    vd = meta.validation_diagnostics
    assert vd is not None
    assert vd["total_rejections"] == 3
    # All 4 LLM groups appear in the dict (groups with 0 rejections show as 0).
    # This is intentional — it lets a reader distinguish "no rejections in
    # this group" from "this group was never invoked."
    assert vd["rejections_by_group"]["identity"] == 1
    assert vd["rejections_by_group"]["offerings"] == 2
    assert vd["rejections_by_group"]["positioning"] == 0
    assert vd["rejections_by_group"]["trust"] == 0
    assert vd["items_dropped"] == {"offerings": 1}
    assert vd["candidates_seen"] == {"offerings": 5}
    # Rejected quotes are stored, grouped — empty groups omitted from this dict
    assert vd["rejected_quotes"]["identity"] == ["some quote"]
    assert vd["rejected_quotes"]["offerings"] == ["another quote", "third"]
    assert "positioning" not in vd["rejected_quotes"]  # empty groups skipped
    assert "trust" not in vd["rejected_quotes"]


def test_diagnostics_truncates_long_quotes():
    """Long rejected quotes must be truncated to 80 chars in the
    persisted structure, so the profile JSON stays compact."""
    long_quote = "x" * 500
    diag = ValidationDiagnostics()
    diag.rejections_by_group["positioning"] = [
        RejectionRecord(code="quote_not_in_block", block_id="b1", quote=long_quote, note=""),
    ]
    meta = _build_meta(_empty_base_meta(), llm_result=None, diagnostics=diag)
    quotes = meta.validation_diagnostics["rejected_quotes"]["positioning"]
    assert len(quotes) == 1
    assert len(quotes[0]) <= 80


def test_diagnostics_records_blacklist_rejections_separately():
    """Blacklist rejections (halal / organic / ISO claims unsupported by
    the cited quote) are a distinct category — surface them separately."""
    diag = ValidationDiagnostics()
    diag.blacklist_rejections["offerings"] = ["halal-claim", "organic-claim"]
    meta = _build_meta(_empty_base_meta(), llm_result=None, diagnostics=diag)
    assert meta.validation_diagnostics["blacklist_rejections"] == {
        "offerings": ["halal-claim", "organic-claim"],
    }


def test_diagnostics_round_trips_via_json():
    """The structured field must serialize cleanly so external readers
    (CLIs, frontends, the benchmark harness) can use the saved profile."""
    diag = ValidationDiagnostics()
    diag.rejections_by_group["identity"] = [
        RejectionRecord(code="block_not_found", block_id="b1", quote="q1", note=""),
    ]
    diag.items_dropped["audience_signals"] = 1

    meta = _build_meta(_empty_base_meta(), llm_result=None, diagnostics=diag)
    raw = meta.model_dump_json()
    reloaded = ExtractionMeta.model_validate_json(raw)
    assert reloaded.validation_diagnostics is not None
    assert reloaded.validation_diagnostics["total_rejections"] == 1
    assert reloaded.validation_diagnostics["items_dropped"] == {"audience_signals": 1}


def test_diagnostics_field_defaults_to_none_for_legacy_meta():
    """A freshly-constructed ExtractionMeta has validation_diagnostics=None.
    Confirms backward compatibility with profiles saved before this PR."""
    meta = ExtractionMeta(manifest_path="x.json", extracted_at=datetime.now(timezone.utc))
    assert meta.validation_diagnostics is None