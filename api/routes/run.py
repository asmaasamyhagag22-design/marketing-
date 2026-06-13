"""POST /api/run — kick off a pipeline job.

Returns immediately with a job_id. The caller subscribes to
GET /api/jobs/{job_id}/stream for live progress.

Pipeline runs in a thread (asyncio.to_thread) so the event loop
stays responsive for SSE streams of other concurrent jobs.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from scraper.url_utils import is_safe_public_url

from ..jobs.runner import has_openai_key, run_pipeline_job
from ..schemas import RunRequest, RunResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/run", response_model=RunResponse)
async def run(req: RunRequest, request: Request) -> RunResponse:
    # SSRF guard: the pipeline fetches this URL server-side, so reject anything
    # that isn't a public http(s) address (blocks localhost / internal ranges /
    # cloud metadata 169.254.169.254).
    if not is_safe_public_url(str(req.url)):
        raise HTTPException(
            status_code=400,
            detail="URL not allowed: must be a public http(s) address (no localhost/internal/metadata hosts).",
        )

    # Fail fast if LLM requested but no key configured.
    if not req.skip_llm and not has_openai_key():
        raise HTTPException(
            status_code=400,
            detail=(
                "OPENAI_API_KEY is not set on the server. "
                "Set the env var or pass skip_llm=true to run rules-only."
            ),
        )

    store = request.app.state.store
    job = store.create()
    # Tell the store which loop will be marshaling events back from the worker.
    store.attach_loop(job.job_id, asyncio.get_running_loop())

    # Spawn the pipeline in a worker thread so we don't block the event loop.
    # Note: we do NOT await this task — fire-and-forget. Status flows back
    # through the store's event queue and the SSE stream.
    asyncio.create_task(_run_in_thread(
        job_id=job.job_id,
        url=str(req.url),
        store=store,
        skip_llm=req.skip_llm,
        model=req.model,
        persist_to_disk=req.persist_to_disk,
    ))

    return RunResponse(job_id=job.job_id)


async def _run_in_thread(
    *, job_id: str, url: str, store, skip_llm: bool,
    model: str, persist_to_disk: bool,
) -> None:
    """Bridge: run the synchronous pipeline in a worker thread."""
    try:
        await asyncio.to_thread(
            run_pipeline_job,
            job_id, url, store,
            skip_llm=skip_llm,
            model=model,
            persist_to_disk=persist_to_disk,
        )
    except Exception as e:  # noqa: BLE001
        # run_pipeline_job already catches and emits its own error events;
        # this is a last-resort guard for failures outside the try block
        # (e.g., asyncio.to_thread itself failing).
        logger.exception("to_thread bridge failed for job %s: %s", job_id, e)
