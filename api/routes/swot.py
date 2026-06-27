"""POST /api/swot/from-profile — competitor-grounded SWOT from a BusinessProfile.

Runs the adaptive discovery router -> comparative matrix -> SWOT synthesis on a
profile already produced by /api/run (the browser holds it after a run, so no
re-scrape and no job-store changes are needed here).

Degrades to a STANDALONE (profile-only) SWOT when no competitors are found —
never empty, never fabricated (matches the CLI behavior).

Note: this path does not re-scrape competitor websites, so the competitor
*scraped* dimensions stay UNKNOWN and the comparison leans on Places signals.
A fuller comparison (re-scraping peers via the run's manifest) is a later slice.
"""
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class SwotFromProfileRequest(BaseModel):
    profile: dict[str, Any]


class SwotItemModel(BaseModel):
    text: str
    citation: List[str]
    evidence: str


class SwotResponse(BaseModel):
    mode: str  # "competitive" | "standalone"
    strengths: List[SwotItemModel]
    weaknesses: List[SwotItemModel]
    opportunities: List[SwotItemModel]
    threats: List[SwotItemModel]
    notes: List[str]
    competitor_count: int


def _items(items) -> List[dict]:
    return [
        {"text": i.text, "citation": list(i.citation), "evidence": i.evidence}
        for i in items
    ]


@router.post("/swot/from-profile", response_model=SwotResponse)
def swot_from_profile(req: SwotFromProfileRequest) -> SwotResponse:
    try:
        from competitor import (
            PlacesClient, route_discovery, build_matrix, synthesize_swot,
        )
        from competitor.swot import unique_insight_texts
        from competitor.web_discovery import default_web_engine

        profile = req.profile

        # Places client is only used for LOCAL/HYBRID routing; if the key is
        # missing or the business is ECOMMERCE/UNKNOWN, discovery degrades safely.
        try:
            client = PlacesClient()
        except Exception:
            client = None

        # ECOMMERCE/HYBRID -> live SERP peer discovery when a search key is set
        # (SERPER_API_KEY/...); None otherwise -> router uses NullWebDiscoveryEngine.
        result = route_discovery(profile, places_client=client,
                                 web_engine=default_web_engine())
        matrix = build_matrix(profile, result.competitors, subject_name="You")
        swot = synthesize_swot(matrix, themes=[],
                               unique_insights=unique_insight_texts(profile))

        return SwotResponse(
            mode=swot.mode,
            strengths=_items(swot.strengths),
            weaknesses=_items(swot.weaknesses),
            opportunities=_items(swot.opportunities),
            threats=_items(swot.threats),
            notes=list(swot.notes),
            competitor_count=len(result.competitors),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"SWOT generation failed: {exc}"
        ) from exc
