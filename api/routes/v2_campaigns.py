"""Authenticated V2 campaign research, exact review and source refresh."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.persistence import get_persistence
from api.routes.auth import require_user
from strategy.campaign_research import load_public_page, research, same_source
from strategy.campaign_v2 import CampaignConflict, CampaignNotFound, propose, refresh


router = APIRouter(prefix="/v2/campaigns")


class StartRequest(BaseModel):
    expected_run_id: UUID | None
    goal: str = Field(min_length=3, max_length=220)
    offer_name: str = Field(min_length=2, max_length=120)
    terms_url: str | None = Field(default=None, max_length=500)


class ReviewRequest(BaseModel):
    run_id: UUID
    decision: Literal["approved", "rejected"]


class RefreshRequest(BaseModel):
    run_id: UUID


def get_page_loader():
    return load_public_page


def get_clock():
    return lambda: datetime.now(timezone.utc)


def store(user=Depends(require_user), clock=Depends(get_clock)):
    persistence = get_persistence()
    if not persistence.supports_canonical_strategy():
        raise HTTPException(503, detail={"code": "POSTGRES_REQUIRED"})
    return persistence.campaigns(user_id=user["id"], clock=clock)


def execute(action):
    try:
        return action()
    except CampaignNotFound:
        raise HTTPException(404, detail={"code": "BRAND_NOT_FOUND"}) from None
    except CampaignConflict as exc:
        raise HTTPException(409, detail={"code": str(exc)}) from None


@router.get("/{domain}")
def current(domain: str, service=Depends(store)):
    return execute(lambda: service.view(domain))


@router.post("/{domain}")
def start(domain: str, request: StartRequest, service=Depends(store),
          loader=Depends(get_page_loader)):
    goal, name = request.goal.strip(), request.offer_name.strip()
    if len(goal) < 3 or len(name) < 2:
        raise HTTPException(422, detail={"code": "GOAL_AND_OFFER_REQUIRED"})
    snapshot = execute(lambda: service.snapshot(domain))
    if snapshot.profile_id is None or not snapshot.source_url:
        raise HTTPException(409, detail={"code": "PROFILE_REQUIRED"})
    if (snapshot.run.id if snapshot.run else None) != request.expected_run_id:
        raise HTTPException(409, detail={"code": "CAMPAIGN_CHANGED"})
    if request.terms_url and not same_source(request.terms_url, snapshot.source_url):
        raise HTTPException(422, detail={"code": "TERMS_MUST_USE_BRAND_ORIGIN"})
    outcome = research(snapshot.source_url, name, loader, now=service.clock(), hint=request.terms_url)
    return execute(lambda: service.write(domain, snapshot, propose(goal, name, outcome)))


@router.post("/{domain}/review")
def review(domain: str, request: ReviewRequest, service=Depends(store)):
    return execute(lambda: service.decide(domain, request.run_id, request.decision))


@router.post("/{domain}/refresh")
def recheck(domain: str, request: RefreshRequest, service=Depends(store),
            loader=Depends(get_page_loader)):
    snapshot = execute(lambda: service.snapshot(domain))
    run = snapshot.run
    if run is None or run.id != request.run_id:
        raise HTTPException(409, detail={"code": "CAMPAIGN_CHANGED"})
    if snapshot.profile_id != run.input_profile_id:
        raise HTTPException(409, detail={"code": "PROFILE_CHANGED"})
    if not run.output.get("watch_url"):
        raise HTTPException(409, detail={"code": "SOURCE_REQUIRED"})
    result = refresh(run.output, loader, service.clock())
    return execute(lambda: service.write(domain, snapshot, result, revision=True))
