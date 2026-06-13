"""FastAPI application entry point.

Run with:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env from the project root BEFORE any pipeline imports run, so that
# OPENAI_API_KEY (and any other env-driven config) is visible to both the
# API layer and to library calls deeper in the pipeline (e.g., OpenAICaller
# reads os.environ at construction time).
#
# We search upwards from this file's directory so the API works whether
# you `cd scraper_v01 && uvicorn api.main:app` or `uvicorn` from elsewhere.
try:
    from dotenv import load_dotenv  # type: ignore

    _search_roots = []
    # First, the current working directory (where uvicorn was started from).
    _search_roots.append(Path.cwd())
    # Then walk up from the file location (covers running from anywhere).
    _here = Path(__file__).resolve()
    _search_roots.append(_here.parent)
    _search_roots.extend(_here.parents)

    _seen: set[Path] = set()
    for root in _search_roots:
        try:
            root_resolved = root.resolve()
        except OSError:
            continue

        if root_resolved in _seen:
            continue

        _seen.add(root_resolved)

        candidate = root_resolved / ".env"
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            break

except ImportError:
    # python-dotenv is optional; the API still works if env is set externally.
    pass


from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .jobs.store import JobStore  # noqa: E402
from .routes import health, jobs, poster, run, swot  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Lifespan: start/stop the JobStore's TTL cleanup task
# ---------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    store = JobStore(ttl_seconds=int(os.environ.get("JOB_TTL_SECONDS", "3600")))
    store.start_cleanup()
    app.state.store = store

    logger.info("JobStore initialized (ttl=%ds)", store._ttl)

    try:
        yield
    finally:
        await store.stop_cleanup()


# ---------------------------------------------------------------------
# App
# ---------------------------------------------------------------------

app = FastAPI(
    title="Marketing Strategist API",
    description=(
        "HTTP wrapper for the evidence-based business profile pipeline. "
        "POST /api/run to start a job, then GET /api/jobs/{id}/stream for live progress. "
        "POST /api/poster/from-profile to generate a printable poster from a profile."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# CORS — allow the Next.js dev server (Day 2) and Vercel deploy (Day 7).
# CORS_ALLOW_ORIGINS env var overrides; comma-separated list of origins.
_default_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://10.2.18.18:3001",
]

_env_origins = os.environ.get("CORS_ALLOW_ORIGINS", "")
if _env_origins.strip():
    allow_origins = [o.strip() for o in _env_origins.split(",") if o.strip()]
else:
    allow_origins = _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------
# Route mounts
# ---------------------------------------------------------------------

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(run.router, prefix="/api", tags=["run"])
app.include_router(jobs.router, prefix="/api", tags=["jobs"])
app.include_router(poster.router, prefix="/api", tags=["poster"])
app.include_router(swot.router, prefix="/api", tags=["swot"])