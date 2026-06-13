"""POST /api/poster/from-profile — generate a poster from a BusinessProfile.

Unified on the NEW pipeline (Poster Studio decisions):
  build_poster_brief -> build_creative_prompt (TEXT-FREE creative concept)
  -> Vertex Imagen -> Playwright HTML/CSS overlay (ultra-minimal: logo + headline
  + CTA; real, Arabic-correct text).

The route is a SYNC `def` on purpose: the renderer uses Playwright's SYNC API,
which cannot run inside the asyncio event loop. FastAPI runs sync routes in a
worker thread, so the sync API is safe there. The response shape is unchanged,
so the existing frontend (poster-studio-card) keeps working.
"""
from __future__ import annotations

import base64
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from poster.from_profile import build_poster_brief
from poster.art_director import build_llm_concept_prompt
from poster.imagen_provider import VertexImagenProvider
from poster.template import render_poster_html
from poster.render_playwright import render_html_to_png
from poster.schemas import (
    BackgroundImageResult,
    PosterArtDirection,
    PosterFromProfileRequest,
    PosterFromProfileResponse,
    PosterRenderResult,
)

router = APIRouter()

# Imagen 4 Ultra has very low default quota/capacity (429s). Fall back to the
# lighter v4 model so the deployed app keeps working.
_FALLBACK_MODEL = "imagen-4.0-generate-001"


def _generate_concept_image(prompt: str) -> tuple[Path, str]:
    """Generate the text-free concept image; on a capacity/quota error, retry
    with a lighter Imagen model. Returns (path, model_used)."""
    provider = VertexImagenProvider()
    try:
        return provider.generate(prompt), provider.model
    except Exception:
        fb = VertexImagenProvider(model=_FALLBACK_MODEL)
        return fb.generate(prompt), fb.model


@router.post("/poster/from-profile", response_model=PosterFromProfileResponse)
def create_poster_from_profile(
    request: PosterFromProfileRequest,
) -> PosterFromProfileResponse:
    try:
        brief = build_poster_brief(request.profile)

        # 1) text-free creative concept image (Vertex Imagen). An LLM art-director
        # invents a unique concept; falls back to the static prompt on error/no key.
        caller = None
        try:
            from business_profile.llm import OpenAICaller
            caller = OpenAICaller()
        except Exception:
            caller = None
        prompt = build_llm_concept_prompt(brief, caller, profile=request.profile)
        bg_path, model_used = _generate_concept_image(prompt)

        # 2) ultra-minimal crisp overlay (Playwright HTML/CSS -> PNG)
        html = render_poster_html(brief, str(bg_path))  # density="minimal" default
        out_dir = Path("outputs/posters")
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"poster_{uuid.uuid4().hex[:8]}.png"
        poster_path = render_html_to_png(html, out_dir / filename)
        image_base64 = base64.b64encode(Path(poster_path).read_bytes()).decode("ascii")

        # Response models kept identical so the frontend needs no changes.
        art_direction = PosterArtDirection(
            provider_prompt=prompt,
            negative_prompt="",
            concept="Text-free creative concept image + ultra-minimal crisp overlay (logo + headline + CTA).",
            category=brief.category or "brand",
            mood="creative-minimal",
            layout="magazine_cover",
            background_style="surreal forced-perspective creative concept",
            safe_overlay_copy=brief.headline or "",
            color_notes=[
                "Image is a TEXT-FREE creative concept (Vertex Imagen).",
                "Logo + minimal real text overlaid via Playwright HTML/CSS (Arabic-correct).",
            ],
            source_fields_used=[
                "business_name", "category", "headline", "cta", "offerings", "palette", "logo",
            ],
        )
        background = BackgroundImageResult(
            provider="vertex-imagen",
            model=model_used,
            prompt=prompt,
            background_path=str(bg_path),
            filename=Path(bg_path).name,
            width=1080,
            height=1350,
            fallback_used=model_used == _FALLBACK_MODEL,
            fallback_reason=("Imagen Ultra capacity/quota (429); used lighter model"
                             if model_used == _FALLBACK_MODEL else None),
        )
        render = PosterRenderResult(
            poster_path=str(poster_path), filename=filename, width=1080, height=1350,
        )

        return PosterFromProfileResponse(
            brief=brief,
            art_direction=art_direction,
            background=background,
            render=render,
            image_base64=image_base64,
        )

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Poster generation failed: {exc}",
        ) from exc
