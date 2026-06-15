"""Creative reel orchestration: Opus director -> Veo 3.1 -> voice-over.

Ties the pieces into the "complete reel" the user asked for:
  1. Opus (vision) designs the reel from the identity + real photos
     (reel.creative_director) — per-scene Veo prompts + voice-over + captions.
  2. Each scene's REAL photo is seeded into Veo 3.1 image-to-video with Opus's
     cinematic motion prompt (so the motion happens INSIDE the real scene).
  3. The voice-over lines are synthesized (reel.voiceover) into a timed track and
     muxed under the visuals (with optional music ducked beneath).

The visuals stay grounded in the brand's real photos; only the motion + narration
are generated. Honest-degrades: no Opus key -> caller should fall back to the
deterministic storyboard; no TTS key -> the reel renders without narration.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from poster.schemas import PosterBrief

from .compositor import render_reel
from .creative_director import CreativeReel, design_creative_reel
from .from_profile import is_rtl
from .schemas import ReelScene, Storyboard
from .video_provider import VideoProvider
from .voiceover import synth_voiceover

logger = logging.getLogger(__name__)


def build_creative_storyboard(reel: CreativeReel, brief: PosterBrief) -> Storyboard:
    """Map an Opus CreativeReel onto the render Storyboard. Each scene carries its
    real-photo seed + Opus's Veo prompt; on-screen text is a short kinetic caption
    (NOT the old repeating headline)."""
    scenes: list[ReelScene] = []
    for s in reel.scenes:
        seed = reel.images[s.image_index] if 0 <= s.image_index < len(reel.images) else None
        scenes.append(ReelScene(
            kind="gallery",
            duration_s=max(1.5, min(s.duration_s, 8.0)),
            visual_prompt=s.veo_prompt,
            seed_image_url=seed,
            sublines=[s.on_screen_text] if s.on_screen_text else [],
            source_field="creative",
        ))
    primary_dir = "rtl" if (reel.language.startswith("ar") or is_rtl(reel.hook)
                            or is_rtl(brief.business_name)) else "ltr"
    return Storyboard(
        business_name=brief.business_name,
        primary_dir=primary_dir,
        total_duration_s=round(sum(s.duration_s for s in scenes), 2),
        scenes=scenes,
        palette_hex=list(brief.palette_hex[:6]),
        primary_color=brief.primary_color,
        tone=brief.tone,
        logo_url=brief.logo_url,
        logo_text=brief.logo_text,
        heading_font=brief.heading_font,
        body_font=brief.body_font,
        content_images=list(reel.images),
        warnings=list(brief.warnings),
    )


def render_creative_reel(
    profile: dict,
    brief: PosterBrief,
    photos: list[str],
    *,
    provider: VideoProvider,
    out_path: str | Path,
    n_scenes: int = 6,
    language: Optional[str] = None,
    scale: float = 1.0,
    include_logo: bool = True,
    music_path: Optional[str | Path] = None,
    with_voiceover: bool = True,
):
    """Full creative pipeline. Returns (render_result, creative_reel) or (None, None)
    when Opus could not design a reel (caller falls back to the normal storyboard)."""
    creative = design_creative_reel(profile, photos, n_scenes=n_scenes, language=language)
    if not creative or not creative.scenes:
        return None, None

    storyboard = build_creative_storyboard(creative, brief)

    vo_path = None
    if with_voiceover:
        vo_lines = [s.voiceover for s in creative.scenes]
        vo_durs = [s.duration_s for s in storyboard.scenes]
        vo_deliveries = [s.voiceover_delivery for s in creative.scenes]
        vo_path = synth_voiceover(vo_lines, vo_durs, Path(out_path).with_suffix(".vo.m4a"),
                                  deliveries=vo_deliveries)
        if vo_path:
            logger.info("voice-over track ready: %s", vo_path)

    result = render_reel(
        storyboard, provider=provider, out_path=out_path,
        scale=scale, include_logo=include_logo,
        music_path=music_path, voiceover_path=vo_path,
    )
    return result, creative
