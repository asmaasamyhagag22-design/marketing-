"""POST /api/reel/from-profile — generate a short vertical reel from a BusinessProfile.

Prefers UNDERSTAND->GENERATE: an LLM director writes a brand-grounded STORY (BrandCreativeDNA as
learned text) -> Imagen text-to-image stills -> Veo 3.1 image-to-video animates each still (Ken
Burns per-scene fallback). Falls back to the Motion engine over the brand's real SCRAPED photos
when generation fails. Composition boundary (this route): a ~2.6s brand END-CARD (big real logo +
CTA pill) is appended, then the kinetic caption layer (HOOK + Ledger-gated story captions; the
end-card replaces the outro beat) is overlaid. SYNC `def` (ffmpeg / Playwright sync can't run in
the event loop; FastAPI runs it in a worker thread). Returns the mp4 as base64."""
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
    caption_beats: list = []
    # 1) UNDERSTAND -> GENERATE from the brand's real ads (the owner's "نفهم ونخترع").
    try:
        from reel.generate import build_brand_generated_reel
        res = build_brand_generated_reel(
            profile, caller=None, out_path=out, n_scenes=request.n_scenes, music_path=None,
            language=request.language,
            log=lambda *_a: None,
        )
        caption_beats = list(getattr(res, "caption_beats", []) or [])
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

    # COMPOSITION BOUNDARY (the engines stay pure footage producers):
    # 2) append the ~2.6s brand END-CARD (big real logo on the brand colour + CTA pill) so the
    #    reel ends on an unmistakable "this is the brand" moment (the owner: "فين WE؟");
    # 3) overlay the kinetic caption layer — HOOK + the story's Ledger-gated captions; when the
    #    end-card landed it replaces the OUTRO beat (no doubled CTA) and the persistent corner
    #    logo fades out before it (the card carries the big logo itself).
    # Both are best-effort — a failure just ships the reel without that layer, never an error.
    from reel.text_overlay import _probe_duration, add_kinetic_text_to_reel

    footage_s = None
    endcard_ok = False
    try:
        from reel.endcard import append_endcard_to_reel
        footage_s = _probe_duration(out)                 # pre-end-card duration (beat window)
        endcard_ok = append_endcard_to_reel(profile, out)
    except Exception:  # noqa: BLE001
        endcard_ok = False
    if not endcard_ok:
        warnings.append("Rendered without the brand end-card.")

    try:
        if not add_kinetic_text_to_reel(
            profile, out, captions=caption_beats or None,
            footage_s=(footage_s if endcard_ok else None),
            include_outro=not endcard_ok,
            hook_override=(getattr(res, "hook", "") if mode == "generated" else ""),
        ):
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
        duration_s=_probe_duration(out) or 0.0,
        scene_count=request.n_scenes,
        mode=mode,
        business_name=name,
        warnings=warnings,
    )
