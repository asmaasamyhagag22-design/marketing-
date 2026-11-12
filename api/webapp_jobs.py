"""Shared job runner for web-app brand-enrichment jobs (analysis, influencer).

A `work(brand)->patch` function runs in a worker thread; the patch, the job's terminal state and its
terminal event are then committed as ONE fact by `finish_enrichment_job`, so polling, result and SSE
cannot disagree about whether the work landed.

`kind` names which stage produced the patch, and every caller must say. Under the legacy backend it
is ignored — the file store has one document and nowhere to record provenance. Under PostgreSQL it
decides which Run the output becomes, and therefore what "current" means for that stage. A default
would have been convenient and wrong: the wrong `kind` files a strategy result as a SWOT, and the
approval gate then guards a document nobody generated.

WHY THE JOB IS NOT CREATED IN `request.app.state.store` ANY MORE. The id returned here is the id the
SPA polls, and under PostgreSQL the answer to that poll lives in the database. Creating the job in
one store and answering from another is the half-lifecycle that was measured to 404 every poll.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import Request

from db.errors import StaleProfileSnapshot

from .persistence import get_persistence

logger = logging.getLogger(__name__)


def start_brand_job(request: Request, domain_key: str, work, *, owner_id: str,
                    kind: str) -> dict:
    """Create a job bound to a brand, run `work` in a thread, persist the patch, mark terminal."""
    job_id = get_persistence().create_user_job(owner_user_id=owner_id, domain_key=domain_key)
    asyncio.create_task(run_brand_job(job_id=job_id, domain_key=domain_key,
                                      work=work, owner_id=owner_id, kind=kind))
    return {"job_id": job_id}


async def run_brand_job(*, job_id: str, domain_key: str, work,
                        owner_id: str = "", kind: str = "swot") -> None:
    """Run one enrichment stage and finalize its job truthfully.

    Takes no store. It used to, and that parameter was the last place a caller could decide where
    job state went — which is the decision the provider now owns. A caller driving this outside a
    request binds the serving store with `api.jobs.store.serving_store` instead.
    """
    persistence = get_persistence()
    persistence_started = False
    try:
        patch, profile_id = await asyncio.to_thread(_do_work, domain_key, work, owner_id)
        if patch is None:
            raise RuntimeError("brand job produced no patch to persist")
        persistence_started = True
        # Scoped: an enrichment job must not be able to rewrite another account's analysis.
        #
        # OFF THE LOOP, for the same reason the work above is: this takes the BrandStore locks (or
        # a brand row lock) and can wait on any competing writer. MEASURED: a 1.5s competing write
        # froze the loop for 1.460s here. The ownership scoping is unchanged — `for_user` is still
        # enforced inside the write, under the storage lock, on the latest committed document.
        persisted = await asyncio.to_thread(
            _persist, job_id, domain_key, patch, owner_id, kind, profile_id)
        if persisted is None:
            raise RuntimeError("required brand persistence was not applied")
    except Exception as e:  # noqa: BLE001
        logger.exception("brand job %s failed: %s", job_id, e)
        safe_error = ("Brand result could not be saved." if persistence_started
                      else "Generation step failed.")
        if isinstance(e, StaleProfileSnapshot):
            safe_error = "Brand evidence changed during analysis. Reload the brand and run analysis again."
        try:
            await asyncio.to_thread(
                persistence.finish_job_failure, job_id=job_id, error=safe_error,
                payload={"error_type": type(e).__name__, "persistence": persistence_started})
        except Exception:  # noqa: BLE001 — logged; the original failure is what matters
            logger.exception("could not terminalize brand job %s", job_id)


def _do_work(domain_key: str, work, owner_id: str = "") -> tuple[Any, str | None]:
    brand = get_persistence().visible_brand(domain_key=domain_key, user_id=owner_id or "") or {}
    profile_id = brand.get("profile_snapshot_id")
    return work(brand), profile_id


def _persist(job_id: str, domain_key: str, patch: Any, owner_id: str, kind: str,
             profile_id: str | None):
    """Record this stage's contribution AND finish the job, in one transaction where there is one.

    Runs OFF the event loop (see the caller). Both backends block — the file store on its process
    and file locks, PostgreSQL on network I/O and a brand row lock — and a competing writer holds
    either for as long as ITS write takes. MEASURED on the file store: a 1.5s competing write froze
    the loop for 1.460s here, which is not one slow request but every request on the process.
    """
    from strategy.positioning.service import CanonicalStrategyBuild

    persistence = get_persistence()
    if isinstance(patch, CanonicalStrategyBuild):
        return persistence.finish_canonical_strategy_job(
            job_id=job_id, domain_key=domain_key, user_id=owner_id or "", build=patch,
            profile_snapshot_id=profile_id,
            payload={"domain_key": domain_key, "decision_type": "POSITIONING"})
    return persistence.finish_enrichment_job(
        job_id=job_id, domain_key=domain_key, user_id=owner_id or "", kind=kind,
        patch=patch, profile_snapshot_id=profile_id if kind == "swot" else None,
        payload={"domain_key": domain_key})
