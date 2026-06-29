"""POST /api/reel/from-profile — generate a short vertical reel from a BusinessProfile.

Prefers UNDERSTAND->GENERATE: the brand's REAL ads (search, attribution-filtered) -> STYLE-generated
on-brand still scenes (Imagen edit) -> the Motion/Music engine (eased motion + xfade). Falls back to
the Motion engine over the brand's real SCRAPED photos when no ad references exist. Never the old
website-photo slideshow with text. SYNC `def` (ffmpeg / Playwright sync can't run in the event loop;
FastAPI runs it in a worker thread). Returns the mp4 as base64 (a data-URI for a <video>)."""
from __future__ import annotations

import base64
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from reel.schemas import REEL_H, REEL_W, ReelFromProfileRequest, ReelFromProfileResponse

router = APIRouter()


@router.post("/reel/from-profile", response_model=ReelFromProfileResponse)
def create_reel_from_profile(request: ReelFromProfileRequest) -> ReelFromProfileResponse:
    profile = request.profile
    out_dir = Path("outputs/reels")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"web_reel_{uuid.uuid4().hex[:8]}.mp4"

    name, palette, warnings = "", [], []
    try:
        from reel.from_profile import build_reel_brief
        brief = build_reel_brief(profile)
        name = brief.business_name
        palette = list(brief.palette_hex or [])
        warnings = list(brief.warnings or [])
    except Exception:  # noqa: BLE001 — brief is best-effort metadata
        pass

    mode = ""
    # 1) UNDERSTAND -> GENERATE from the brand's real ads (the owner's "نفهم ونخترع").
    try:
        from reel.generate import build_brand_generated_reel
        build_brand_generated_reel(
            profile, caller=None, out_path=out, n_scenes=request.n_scenes, music_path=None,
            log=lambda *_a: None,
        )
        mode = "generated"
    except Exception as gen_exc:  # noqa: BLE001
        # 2) FALLBACK: the Motion engine over the brand's real scraped photos (no website slideshow).
        try:
            from reel.image_quality import filter_usable_photos
            from reel.motion import build_motion_reel
            imgs = (profile.get("visual") or {}).get("content_images") or []
            usable = filter_usable_photos(imgs, max_keep=max(2, request.n_scenes + 2))
            if not usable:
                raise RuntimeError(
                    f"no brand-ad references and no usable scraped photos to build from ({gen_exc})"
                )
            build_motion_reel(usable, out, palette=palette, music_path=None)
            mode = "motion"
            warnings.append("Generated from the brand's real scraped photos (no ad references found).")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Reel generation failed: {exc}") from exc

    # Overlay the kinetic CAPTION layer (HOOK headline + CTA pill) onto the cinematic
    # video. Best-effort — the motion/generate engines are text-free by design, so a
    # failure here just returns the text-free reel rather than erroring.
    try:
        from reel.text_overlay import add_kinetic_text_to_reel
        if not add_kinetic_text_to_reel(profile, out):
            warnings.append("Rendered without the kinetic text overlay.")
    except Exception:  # noqa: BLE001
        warnings.append("Rendered without the kinetic text overlay.")

    try:
        data = out.read_bytes()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Reel render produced no file: {exc}") from exc

    return ReelFromProfileResponse(
        video_base64=base64.b64encode(data).decode("ascii"),
        filename=out.name,
        width=REEL_W,
        height=REEL_H,
        scene_count=request.n_scenes,
        mode=mode,
        business_name=name,
        warnings=warnings,
    )
