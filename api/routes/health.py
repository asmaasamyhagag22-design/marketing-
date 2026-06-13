"""Health check endpoint.

Trivial; used by Railway / Vercel / load balancers to confirm the
process is up. Also a good first endpoint to hit when debugging the
local setup.
"""
from __future__ import annotations

from fastapi import APIRouter

from ..schemas import HealthResponse

router = APIRouter()

_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=_VERSION)
