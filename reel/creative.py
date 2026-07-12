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
from typing import Any, Optional

from poster.schemas import PosterBrief

from .compositor import render_reel
from .creative_director import CreativeReel, design_creative_reel
from .from_profile import is_rtl
from .schemas import ReelScene, Storyboard
from .video_provider import VideoProvider
from .voiceover import synth_voiceover

logger = logging.getLogger(__name__)


def _brand_tone(profile: Any) -> str:
    """The brand's tone-of-voice value (e.g. 'luxury') from the profile, so the voice-over
    delivery fits the brand instead of a hardcoded read. Robust to the {'profile': {...}} wrapper."""
    try:
        p = profile.get("profile", profile) if isinstance(profile, dict) else {}
        t = p.get("tone_of_voice")
        if isinstance(t, dict):
            t = t.get("value")
        return str(t or "").lower()
    except Exception:
        return ""


def build_creative_storyboard(reel: CreativeReel, brief: PosterBrief) -> Storyboard:
    """Map an Opus CreativeReel onto the render Storyboard. Each scene carries its
    real-photo seed + Opus's Veo prompt; on-screen text is a short kinetic caption
    (NOT the old repeating headline)."""
    scenes: list[ReelScene] = []
    n = len(reel.scenes)
    for idx, s in enumerate(reel.scenes):
        seed = reel.images[s.image_index] if 0 <= s.image_index < len(reel.images) else None
        cap = (s.on_screen_text or "").strip()
        words = len(cap.split())
        # READABLE PACING (owner: 'the text goes by too fast'): a captioned scene must hold long
        # enough to READ — research CPS rule ~ 1.5s + 0.35s/word, hard 3s floor for a phrase.
        base = max(1.5, min(s.duration_s, 8.0))
        dur = min(8.0, max(base, 3.0, 1.5 + 0.35 * words)) if cap else base
        # DESIGNED captions (owner: 'text with no design'): route the caption into the fields that
        # trigger the template's DESIGNED styles — scene 0 -> the hero LOCKUP + logo (kind=intro),
        # the last scene -> the accent CTA CHIP + logo (kind=outro), middle captions -> the big
        # display .headline (NOT the tiny flat .item subline the gallery path used before).
        kind, headline, cta_text = "gallery", "", ""
        if cap and idx == 0:
            kind, headline = "intro", cap
        elif cap and idx == n - 1:
            kind, cta_text = "outro", cap
        elif cap:
            headline = cap
        scenes.append(ReelScene(
            kind=kind,
            duration_s=round(dur, 2),
            visual_prompt=s.veo_prompt,
            seed_image_url=seed,
            headline=headline,
            cta_text=cta_text,
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
    featured_product: Optional[str] = None,
    plan_override: Optional[dict] = None,
):
    """Full creative pipeline. Returns (render_result, creative_reel) or (None, None)
    when Opus could not design a reel (caller falls back to the normal storyboard).
    `featured_product` (set when the user picked one) makes the WHOLE reel about that item."""
    # HITL (owner law 2026-07-12): a user-APPROVED plan replaces the director call
    # verbatim; every downstream gate (plan_eval, scene_qa, grounding) still runs on it.
    if plan_override:
        from reel.creative_director import CreativeReel
        try:
            creative = CreativeReel.model_validate(plan_override)
        except Exception:
            creative = None
    else:
        creative = design_creative_reel(profile, photos, n_scenes=n_scenes, language=language,
                                        featured_product=featured_product)
    if not creative or not creative.scenes:
        return None, None

    # PRE-RENDER EVAL (owner: 'evaluate the reel before it comes out'): score the PLAN against the
    # stranger test + caption rules BEFORE the 10-15 min Veo render. A weak plan is regenerated once
    # (a cheap Opus call) rather than rendered; the compositor's scene_qa still checks each rendered
    # clip afterwards. Deterministic, so it never adds a network dependency.
    try:
        from reel.plan_eval import evaluate_reel_plan
        verdict = evaluate_reel_plan(creative, profile=profile, featured=bool(featured_product))
        if not verdict.ok:
            logger.info("reel plan eval: score=%d issues=%s -> regenerating once",
                        verdict.score, verdict.issues)
            retry = design_creative_reel(profile, photos, n_scenes=n_scenes, language=language,
                                         featured_product=featured_product)
            if retry and retry.scenes:
                v2 = evaluate_reel_plan(retry, profile=profile, featured=bool(featured_product))
                if v2.score >= verdict.score:                 # keep the stronger plan
                    creative, verdict = retry, v2
            logger.info("reel plan eval (final): score=%d issues=%s", verdict.score, verdict.issues)
    except Exception:  # noqa: BLE001 — the eval must never block a render
        pass

    storyboard = build_creative_storyboard(creative, brief)

    vo_path = None
    if with_voiceover:
        vo_lines = [s.voiceover for s in creative.scenes]
        vo_durs = [s.duration_s for s in storyboard.scenes]
        vo_deliveries = [s.voiceover_delivery for s in creative.scenes]
        vo_path = synth_voiceover(vo_lines, vo_durs, Path(out_path).with_suffix(".vo.m4a"),
                                  deliveries=vo_deliveries, tone=_brand_tone(profile))
        if vo_path:
            logger.info("voice-over track ready: %s", vo_path)

    # SCENE QA (featured single product): a Gemini vision caller inspects each generated clip and
    # rejects Veo hallucinations — the product redrawn/unfaithful, VANISHING mid-scene, or an
    # IMPOSSIBLE action (a sealed pump pressed) — regenerating once, then falling back to the
    # faithful real photo. Only when a product is featured (that's the item that must stay true).
    qa_caller = None
    qa_ref = None
    if featured_product:
        try:
            from business_profile.llm import default_caller
            qa_caller = default_caller(strong=True)
        except Exception:
            qa_caller = None
        seed_url = storyboard.content_images[0] if storyboard.content_images else None
        if qa_caller is not None and seed_url:
            try:
                from reel.video_provider import _load_reference_image
                loaded = _load_reference_image(seed_url)
                qa_ref = loaded[0] if loaded else None
            except Exception:
                qa_ref = None

    result = render_reel(
        storyboard, provider=provider, out_path=out_path,
        scale=scale, include_logo=include_logo,
        music_path=music_path, voiceover_path=vo_path,
        qa_caller=qa_caller, qa_product_hint=featured_product, qa_reference_image=qa_ref,
    )
    return result, creative
