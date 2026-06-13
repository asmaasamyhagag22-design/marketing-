"""In-memory job store.

Each Job carries:
- a JobStatus
- a history of StageEvents (for snapshot + late-subscriber catch-up)
- an asyncio.Queue used by the SSE endpoint to stream events live
- a reference to the asyncio loop that owns the queue (so the worker
  thread can push events safely via call_soon_threadsafe)
- the final BusinessProfile JSON when the job succeeds
- audit paths: where the manifest and profile were written

Design notes:
- One asyncio.Queue per job; the SSE stream reads from it; the runner
  thread writes to it via call_soon_threadsafe(queue.put_nowait, event).
- Events go to BOTH the queue (for live streamers) AND `events` list
  (for snapshots / catch-up). When the SSE endpoint starts streaming,
  it first replays the events list, then awaits the queue.
- TTL cleanup runs in a background task; defaults to 1 hour after the
  job reaches a terminal state. Old jobs are evicted to keep memory bounded.

Thread-safety:
- All mutations of Job fields happen either on the event loop OR
  inside the runner's emit() helper which marshals back to the loop.
- The internal dict is guarded by an asyncio.Lock when iterated, but
  reads of individual jobs by id don't need a lock — the dict reference
  is stable for the job's lifetime.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ..schemas import JobStatus, Stage, StageEvent, StageStatus

logger = logging.getLogger(__name__)


# Sentinel event meaning "stream is closing; stop listening".
_STREAM_CLOSE = object()


@dataclass
class Job:
    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    current_stage: Optional[Stage] = None
    error: Optional[str] = None
    events: list[StageEvent] = field(default_factory=list)
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    # The loop that owns `queue`. Cross-thread pushes use call_soon_threadsafe(loop, ...).
    loop: Optional[asyncio.AbstractEventLoop] = None
    # Audit paths
    manifest_path: Optional[str] = None
    profile_path: Optional[str] = None
    # Final result (the BusinessProfile as a plain dict for HTTP serialization)
    result: Optional[dict[str, Any]] = None
    # When the job finished (terminal state). Used for TTL.
    finished_at: Optional[float] = None  # time.monotonic()

    def is_terminal(self) -> bool:
        return self.status in (JobStatus.SUCCEEDED, JobStatus.FAILED)


class JobStore:
    """Process-local job registry.

    Single instance per app, mounted on `app.state.store`. Not safe
    for multi-process deployment; for that we'd swap to Redis-backed
    storage. Fine for single-container demo deploys (Railway).
    """

    def __init__(self, ttl_seconds: int = 3600):
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds
        self._cleanup_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_cleanup(self) -> None:
        """Start the periodic TTL cleanup task. Called on app startup."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self) -> None:
        """Evict terminal jobs older than TTL. Loops forever until cancelled."""
        try:
            while True:
                await asyncio.sleep(min(self._ttl, 300))  # at most every 5 min
                now = time.monotonic()
                async with self._lock:
                    expired = [
                        jid for jid, j in self._jobs.items()
                        if j.is_terminal() and j.finished_at
                        and (now - j.finished_at) > self._ttl
                    ]
                    for jid in expired:
                        del self._jobs[jid]
                if expired:
                    logger.info("Evicted %d expired jobs", len(expired))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("Cleanup loop crashed: %s", e)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self) -> Job:
        """Create a new job in QUEUED state. Caller must call attach_loop()
        before the runner starts so cross-thread event pushes work."""
        job_id = uuid.uuid4().hex[:16]
        now = datetime.now(timezone.utc)
        job = Job(
            job_id=job_id,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
        self._jobs[job_id] = job
        return job

    def attach_loop(self, job_id: str, loop: asyncio.AbstractEventLoop) -> None:
        """Record the asyncio loop that owns this job's queue. The runner
        thread uses this loop to push events safely."""
        job = self._jobs.get(job_id)
        if job is not None:
            job.loop = loop

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    # ------------------------------------------------------------------
    # Mutations — called either by the runner (via emit_threadsafe) or
    # by HTTP handlers on the event loop.
    # ------------------------------------------------------------------

    def append_event(self, job_id: str, event: StageEvent) -> None:
        """Record an event, update job status, and push to the queue.

        Must be called on the asyncio loop. The runner thread uses
        emit_threadsafe() which schedules this method on the loop.
        """
        job = self._jobs.get(job_id)
        if job is None:
            logger.warning("append_event: unknown job_id=%s", job_id)
            return
        job.events.append(event)
        job.updated_at = event.timestamp
        # Status transitions driven by the event stream:
        if event.status == StageStatus.STARTED:
            job.status = JobStatus.RUNNING
            job.current_stage = event.stage
        elif event.status == StageStatus.ERROR:
            job.status = JobStatus.FAILED
            job.error = event.error
            job.finished_at = time.monotonic()
        elif event.stage == Stage.FINAL and event.status == StageStatus.DONE:
            job.status = JobStatus.SUCCEEDED
            job.current_stage = None
            job.finished_at = time.monotonic()
        # Push to live queue (non-blocking by design — queue is unbounded)
        try:
            job.queue.put_nowait(event)
        except Exception as e:  # noqa: BLE001
            logger.exception("Queue put failed for job %s: %s", job_id, e)
        # If terminal, push a close sentinel so the SSE stream can exit cleanly
        if job.is_terminal():
            try:
                job.queue.put_nowait(_STREAM_CLOSE)
            except Exception:
                pass

    def emit_threadsafe(self, job_id: str, event: StageEvent) -> None:
        """Thread-safe entry point used by the runner thread.

        Schedules append_event() on the job's loop. If the loop is gone
        (job evicted), the event is silently dropped.
        """
        job = self._jobs.get(job_id)
        if job is None or job.loop is None:
            return
        try:
            job.loop.call_soon_threadsafe(self.append_event, job_id, event)
        except RuntimeError as e:
            # Loop has shut down — drop silently
            logger.debug("Loop closed for job %s: %s", job_id, e)

    def set_result(
        self, job_id: str, result: dict[str, Any],
        manifest_path: Optional[str] = None,
        profile_path: Optional[str] = None,
    ) -> None:
        """Attach the final result + audit paths. Safe to call on the loop."""
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.result = result
        job.manifest_path = manifest_path
        job.profile_path = profile_path

    def set_result_threadsafe(
        self, job_id: str, result: dict[str, Any],
        manifest_path: Optional[str] = None,
        profile_path: Optional[str] = None,
    ) -> None:
        job = self._jobs.get(job_id)
        if job is None or job.loop is None:
            return
        try:
            job.loop.call_soon_threadsafe(
                self.set_result, job_id, result, manifest_path, profile_path,
            )
        except RuntimeError:
            pass

    def all_job_ids(self) -> list[str]:
        return list(self._jobs.keys())


# ---------------------------------------------------------------------
# Dependency-style accessor (for use in route handlers)
# ---------------------------------------------------------------------

def get_store(app) -> JobStore:
    """Return the JobStore mounted on the FastAPI app."""
    return app.state.store


# Re-export the close sentinel for the SSE route
STREAM_CLOSE = _STREAM_CLOSE
