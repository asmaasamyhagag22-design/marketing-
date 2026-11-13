"""Authenticated V2 campaign research, exact review and source refresh."""
from datetime import datetime, timezone
from threading import BoundedSemaphore
from typing import Literal
from uuid import UUID
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from api.brand_translate import domain_key_from_url
from api.persistence import get_persistence
from api.routes.auth import require_user
from api.user_auth import webapp_dir
from strategy.campaign_package import Brief, load_package_page, proposal, research_package, valid_source_url, validate_sources
from strategy.campaign_planner import BriefReview, PlanInput, build_plan, refresh_plan, review_draft
from strategy.campaign_research import load_public_page, research, same_source
from strategy.campaign_v2 import CampaignConflict, CampaignNotFound, propose, refresh


router = APIRouter(prefix="/v2/campaigns")
export_slot = BoundedSemaphore(1)
research_slots = BoundedSemaphore(3)


class StartRequest(BaseModel):
    expected_run_id: UUID | None
    goal: Literal["TRIAL_BOOKINGS"]
    booking_target: int | None = Field(default=None, ge=1, le=1_000_000)
    offer_name: str = Field(min_length=2, max_length=120)
    terms_url: str | None = Field(default=None, max_length=500)


class PackageRequest(BaseModel):
    expected_run_id: UUID | None
    brief: Brief


class PlanRequest(PlanInput):
    request_id: UUID
    expected_run_id: UUID | None = None


class BriefReviewRequest(BriefReview):
    run_id: UUID


class DirectionRequest(BaseModel):
    run_id: UUID
    selected: int = Field(ge=0, le=2)


class ReviewRequest(BaseModel):
    run_id: UUID
    decision: Literal["approved", "rejected"]


class RefreshRequest(BaseModel):
    run_id: UUID


def get_page_loader():
    return load_public_page


def get_package_loader():
    return load_package_page


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


@router.get("/planning-state")
def planning_state(url: str, service=Depends(store)):
    if len(url) > 500 or not valid_source_url(url):
        raise HTTPException(422, detail={"code": "INVALID_SOURCE_URL"})
    snapshot = execute(lambda: service.planning_snapshot(domain_key_from_url(url)))
    return {"run_id": str(snapshot.run.id) if snapshot and snapshot.run else None}


@router.post("/plan")
def plan_campaign(request: PlanRequest, service=Depends(store), loader=Depends(get_package_loader)):
    def generate():
        if not valid_source_url(request.url):
            raise CampaignConflict("INVALID_SOURCE_URL")
        domain = domain_key_from_url(request.url)
        snapshot = service.planning_snapshot(domain)
        current = snapshot.run if snapshot else None
        inputs = PlanInput(url=request.url, objective=request.objective, language=request.language)
        if snapshot:
            replay = service.replay_plan(domain, request.request_id, inputs.model_dump(mode="json"))
            if replay:
                return {"domain_key": domain, **replay}
        if (current.id if current else None) != request.expected_run_id:
            raise CampaignConflict("CAMPAIGN_CHANGED")
        if snapshot and not snapshot.profile_id:
            raise CampaignConflict("PROFILE_REQUIRED")
        if snapshot and snapshot.source_url and not same_source(request.url, snapshot.source_url):
            raise CampaignConflict("BRAND_SOURCE_ORIGIN_MISMATCH")
        if not research_slots.acquire(blocking=False):
            raise HTTPException(503, detail={"code": "CAMPAIGN_RESEARCH_BUSY"})
        try:
            name = (snapshot.brand_name if snapshot else "") or urlsplit(request.url).hostname
            result = build_plan(inputs, name, loader, service.clock, request_id=str(request.request_id))
            return {"domain_key": domain, **service.write_plan(domain, snapshot, result, request.url)}
        finally:
            research_slots.release()

    return execute(generate)


@router.post("/{domain}/brief")
def save_brief(domain: str, request: BriefReviewRequest, service=Depends(store)):
    def revise():
        snapshot = package_snapshot(service, domain, request.run_id)
        run = snapshot.run
        if run.input_profile_id != snapshot.profile_id:
            raise CampaignConflict("PROFILE_CHANGED")
        view = service.view(domain)
        if view["run_id"] != str(run.id):
            raise CampaignConflict("CAMPAIGN_CHANGED")
        if not run.output.get("planner") or not run.output["brief"]:
            raise CampaignConflict("PLANNED_BRIEF_REQUIRED")
        if view["reason"] not in (None, "BRIEF_REVIEW_REQUIRED"):
            raise CampaignConflict(view["reason"])
        result = review_draft(run.output, request)
        if not result["changes"] and run.output["planner"]["brief_reviewed"]:
            return service.write(domain, snapshot, None)
        return service.write(domain, snapshot, result, revision=True)

    return execute(revise)


@router.get("/{domain}")
def current(domain: str, service=Depends(store)):
    return execute(lambda: service.view(domain))


@router.post("/{domain}")
def start(domain: str, request: StartRequest, service=Depends(store),
          loader=Depends(get_page_loader)):
    name = request.offer_name.strip()
    if len(name) < 2:
        raise HTTPException(422, detail={"code": "OFFER_NAME_REQUIRED"})
    snapshot = execute(lambda: service.snapshot(domain))
    if snapshot.profile_id is None or not snapshot.source_url:
        raise HTTPException(409, detail={"code": "PROFILE_REQUIRED"})
    if (snapshot.run.id if snapshot.run else None) != request.expected_run_id:
        raise HTTPException(409, detail={"code": "CAMPAIGN_CHANGED"})
    if request.terms_url and not same_source(request.terms_url, snapshot.source_url):
        raise HTTPException(422, detail={"code": "TERMS_MUST_USE_BRAND_ORIGIN"})
    outcome = research(snapshot.source_url, name, loader, clock=service.clock, hint=request.terms_url)
    proposal = propose(name, outcome, brand_name=snapshot.brand_name, booking_target=request.booking_target)
    return execute(lambda: service.write(domain, snapshot, proposal))


@router.post("/{domain}/review")
def review(domain: str, request: ReviewRequest, service=Depends(store)):
    return execute(lambda: service.decide(domain, request.run_id, request.decision))


def package_snapshot(service, domain, expected_run_id):
    snapshot = service.snapshot(domain)
    if snapshot.profile_id is None or not snapshot.source_url:
        raise CampaignConflict("PROFILE_REQUIRED")
    if (snapshot.run.id if snapshot.run else None) != expected_run_id:
        raise CampaignConflict("CAMPAIGN_CHANGED")
    return snapshot


@router.post("/{domain}/package")
def create_package(domain: str, request: PackageRequest, service=Depends(store),
                   loader=Depends(get_package_loader)):
    def create():
        snapshot = package_snapshot(service, domain, request.expected_run_id)
        validate_sources(request.brief, snapshot.source_url)
        result = research_package(request.brief, snapshot.brand_name or domain, loader, service.clock)
        return service.write(domain, snapshot, result, revision=snapshot.run is not None)

    return execute(create)


@router.post("/{domain}/direction")
def revise_direction(domain: str, request: DirectionRequest, service=Depends(store)):
    def revise():
        snapshot = package_snapshot(service, domain, request.run_id)
        run = snapshot.run
        if run.input_profile_id != snapshot.profile_id:
            raise CampaignConflict("PROFILE_CHANGED")
        previous = run.output
        if previous.get("kind") != "SOURCE_CAMPAIGN" or previous["status"] != "READY":
            raise CampaignConflict("PACKAGE_REQUIRED")
        brief = Brief.model_validate(previous["brief"])
        if previous.get("planner"):
            if request.selected == brief.selected:
                return service.write(domain, snapshot, None)
            result = review_draft(previous, BriefReview(audience=brief.audience, tone=brief.tone, selected=request.selected))
            return service.write(domain, snapshot, result, revision=True)
        if request.selected == brief.selected:
            return service.write(domain, snapshot, None)
        old_direction = brief.directions[brief.selected].name
        brief = brief.model_copy(update={"selected": request.selected})
        result = proposal(brief, previous["brand_name"], previous["evidence"], changes=[{
            "field": "direction", "before": old_direction, "after": brief.directions[brief.selected].name,
        }])
        return service.write(domain, snapshot, result, revision=True)

    return execute(revise)


def current_package(service, domain, run_id, *, require_approval):
    view = service.view(domain)
    if view["run_id"] != str(run_id):
        raise CampaignConflict("CAMPAIGN_CHANGED")
    if view["proposal"].get("kind") != "SOURCE_CAMPAIGN":
        raise CampaignConflict("PACKAGE_REQUIRED")
    if view["reason"]:
        raise CampaignConflict(view["reason"])
    if require_approval and not view["approved"]:
        raise CampaignConflict("CURRENT_PACKAGE_APPROVAL_REQUIRED")
    return view


def render_package(service, domain, run_id, renderer, *, require_approval):
    from poster.campaign_package import PosterLayoutError

    view = current_package(service, domain, run_id, require_approval=require_approval)
    if not export_slot.acquire(blocking=False):
        raise HTTPException(503, detail={"code": "EXPORT_BUSY"})
    try:
        try:
            from playwright.sync_api import Error as BrowserError
        except ImportError:
            raise HTTPException(503, detail={"code": "POSTER_RENDER_UNAVAILABLE"}) from None
        try:
            output = renderer(view)
        except PosterLayoutError as exc:
            raise CampaignConflict(str(exc)) from None
        except (BrowserError, OSError):
            raise HTTPException(503, detail={"code": "POSTER_RENDER_UNAVAILABLE"}) from None
        latest = current_package(service, domain, run_id, require_approval=require_approval)
        if require_approval and latest["approval_id"] != view["approval_id"]:
            raise CampaignConflict("CURRENT_PACKAGE_APPROVAL_REQUIRED")
        return output
    finally:
        export_slot.release()


@router.get("/{domain}/package/preview")
def preview_package(domain: str, run_id: UUID, size: Literal["portrait", "square"], service=Depends(store)):
    from poster.campaign_package import preview_poster

    image = execute(lambda: render_package(
        service, domain, run_id, lambda view: preview_poster(view, size, webapp_dir() / "campaign-posters"),
        require_approval=False,
    ))
    return Response(image, media_type="image/png", headers={"Cache-Control": "private, no-store"})


@router.get("/{domain}/package/export")
def download_package(domain: str, run_id: UUID, service=Depends(store)):
    from poster.campaign_package import export_package

    bundle = execute(lambda: render_package(
        service, domain, run_id, lambda view: export_package(view, webapp_dir() / "campaign-posters"),
        require_approval=True,
    ))
    return Response(bundle, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="adzy-{run_id}.zip"',
        "Cache-Control": "private, no-store",
    })


@router.post("/{domain}/refresh")
def recheck(domain: str, request: RefreshRequest, service=Depends(store),
            loader=Depends(get_page_loader), package_loader=Depends(get_package_loader)):
    snapshot = execute(lambda: service.snapshot(domain))
    run = snapshot.run
    if run is None or run.id != request.run_id:
        raise HTTPException(409, detail={"code": "CAMPAIGN_CHANGED"})
    if snapshot.profile_id != run.input_profile_id:
        raise HTTPException(409, detail={"code": "PROFILE_CHANGED"})
    if run.output.get("planner"):
        if not research_slots.acquire(blocking=False):
            raise HTTPException(503, detail={"code": "CAMPAIGN_RESEARCH_BUSY"})
        try:
            result = refresh_plan(run.output, package_loader, service.clock)
            return execute(lambda: service.write(domain, snapshot, result, revision=True))
        finally:
            research_slots.release()
    if run.output.get("kind") == "SOURCE_CAMPAIGN":
        brief = Brief.model_validate(run.output["brief"])
        result = research_package(brief, run.output["brand_name"], package_loader, service.clock, run.output)
        return execute(lambda: service.write(domain, snapshot, result, revision=True))
    if not run.output.get("watch_url"):
        raise HTTPException(409, detail={"code": "SOURCE_REQUIRED"})
    result = refresh(run.output, loader, service.clock)
    return execute(lambda: service.write(domain, snapshot, result, revision=True))
