"""Production hardening tests: no silent LLM success in the API layer.

When skip_llm=False but every LLM group call fails, the API runner
must emit the LLM stage DONE event with a 'warning' field, and the
MERGE/FINAL events must carry llm_silent_failure=True and
ready_for_poster=False.

The frontend's diagnostics panel reads these to render a red banner;
this test guards the contract.
"""
from __future__ import annotations

import asyncio
import sys
import types

# Stub playwright before importing scraper-dependent modules
_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from api.jobs.runner import run_pipeline_job  # noqa: E402
from api.jobs.store import JobStore  # noqa: E402
from api.schemas import JobStatus, Stage  # noqa: E402
from business_profile.llm.caller import MockCaller  # noqa: E402

from tests.test_api_run import _fake_scraper_fn  # noqa: E402
from tests.test_merger import _full_staged_responses  # noqa: E402


def _broken_caller_factory():
    """Mock caller that fails every group call → silent failure scenario."""
    return MockCaller(
        _full_staged_responses(),
        raise_on_group={"identity", "offerings", "positioning", "trust"},
        model="gpt-4o-mini",
    )


def test_llm_silent_failure_emits_warning_in_sse_payload():
    """Run a job where all 4 LLM groups fail. The LLM:done event must
    carry a non-null 'warning' string mentioning silent failure."""
    async def run_test():
        store = JobStore(ttl_seconds=60)
        job = store.create()
        store.attach_loop(job.job_id, asyncio.get_running_loop())
        await asyncio.to_thread(
            run_pipeline_job,
            job.job_id, "https://example.com/", store,
            skip_llm=False,
            persist_to_disk=False,
            caller_factory=_broken_caller_factory,
            scraper_fn=_fake_scraper_fn,
        )
        await asyncio.sleep(0)
        return store, job.job_id

    store, job_id = asyncio.run(run_test())
    job = store.get(job_id)
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED  # pipeline finished, but LLM was silent

    # Find the LLM DONE event
    llm_events = [
        e for e in job.events
        if e.stage == Stage.LLM and e.status.value == "done"
    ]
    assert llm_events, "no LLM done event emitted"
    payload = llm_events[-1].payload or {}
    assert payload.get("calls") == 0
    assert payload.get("warning") is not None, (
        f"expected non-null warning on llm:done payload, got {payload}"
    )
    assert "silent" in str(payload["warning"]).lower()


def test_llm_silent_failure_blocks_poster_readiness():
    """Same scenario: the MERGE event payload must show
    ready_for_poster=False and llm_silent_failure=True."""
    async def run_test():
        store = JobStore(ttl_seconds=60)
        job = store.create()
        store.attach_loop(job.job_id, asyncio.get_running_loop())
        await asyncio.to_thread(
            run_pipeline_job,
            job.job_id, "https://example.com/", store,
            skip_llm=False, persist_to_disk=False,
            caller_factory=_broken_caller_factory,
            scraper_fn=_fake_scraper_fn,
        )
        await asyncio.sleep(0)
        return store, job.job_id

    store, job_id = asyncio.run(run_test())
    job = store.get(job_id)

    merge_done = [
        e for e in job.events
        if e.stage == Stage.MERGE and e.status.value == "done"
    ]
    assert merge_done, "no MERGE done event"
    payload = merge_done[-1].payload or {}
    assert payload.get("ready_for_poster") is False
    assert payload.get("llm_silent_failure") is True
    blockers = payload.get("poster_blockers") or []
    assert "llm_silent_failure" in blockers


def test_normal_pipeline_emits_no_llm_warning():
    """Sanity: when LLM runs OK, the llm:done event has warning=None."""
    async def run_test():
        store = JobStore(ttl_seconds=60)
        job = store.create()
        store.attach_loop(job.job_id, asyncio.get_running_loop())
        await asyncio.to_thread(
            run_pipeline_job,
            job.job_id, "https://example.com/", store,
            skip_llm=False, persist_to_disk=False,
            caller_factory=lambda: MockCaller(
                _full_staged_responses(), model="gpt-4o-mini",
            ),
            scraper_fn=_fake_scraper_fn,
        )
        await asyncio.sleep(0)
        return store, job.job_id

    store, job_id = asyncio.run(run_test())
    job = store.get(job_id)
    llm_done = [
        e for e in job.events
        if e.stage == Stage.LLM and e.status.value == "done"
    ]
    assert llm_done
    payload = llm_done[-1].payload or {}
    assert payload.get("calls") == 4
    assert payload.get("warning") is None
