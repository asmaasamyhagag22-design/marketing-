"""brief (+ profile) -> storyboard: compose timed, evidence-only scenes.

ZERO HALLUCINATION: a scene is emitted ONLY when it has real verbatim content. The
intro (brand headline) and outro (name + scraped CTA) always have content; the
offering / value-prop / contact scenes are skipped when their profile fields are
empty — the reel never pads with invented copy.

Each scene's visual is a text-free, vertical-appropriate Veo prompt (people +
place) from `reel.art_director`; the words are overlaid verbatim afterward.
"""
from __future__ import annotations

from typing import Any, Optional

from poster.schemas import PosterBrief

from .art_director import build_brand_scene, build_scene_prompt
from .from_profile import is_rtl
from .schemas import ReelScene, Storyboard

# Default per-scene seconds (before length-fitting).
_INTRO_S = 3.5
_OFFERING_BASE_S = 2.6
_OFFERING_PER_ITEM_S = 0.8
_VALUE_S = 4.0
_CONTACT_S = 3.4
_OUTRO_S = 3.2

_MIN_SCENE_S = 1.5

# Drop order when over the length cap (intro + outro are never dropped).
_DROP_PRIORITY = ["value_prop", "contact", "offering"]


def _social_lines(brief: PosterBrief, limit: int = 2) -> list[str]:
    """Verbatim social platform labels for the contact scene."""
    out: list[str] = []
    for s in brief.social:
        label = (s.platform or "").strip()
        if label and label.lower() not in {x.lower() for x in out}:
            out.append(label)
        if len(out) >= limit:
            break
    return out


def _contact_lines(brief: PosterBrief, profile: Optional[dict]) -> list[str]:
    """Actionable contact lines, phone FIRST. Uses the CLEAN e164 number (the
    scraped `raw` can contain junk); falls back to a short-code's raw only when
    explicitly flagged. Then WhatsApp, email, and a couple of social labels."""
    lines: list[str] = []
    cc = (profile or {}).get("contact_channels") or {}

    for ph in (cc.get("phones") or []):
        if not isinstance(ph, dict):
            continue
        num = (ph.get("e164") or "").strip()
        if not num and ph.get("is_short_code"):
            num = (ph.get("raw") or "").strip()
        if num and len(num) <= 20:          # guard against junk-filled raw
            lines.append(num)
            break
    for wa in (cc.get("whatsapp_numbers") or []):
        if wa:
            lines.append(str(wa).strip())
            break
    for em in (cc.get("emails") or []):
        if em:
            lines.append(str(em).strip())
            break

    if not lines and brief.contact_line:    # profile-less fallback
        lines.append(brief.contact_line)

    lines.extend(_social_lines(brief))

    out, seen = [], set()
    for line in lines:
        key = line.lower()
        if line and key not in seen:
            seen.add(key)
            out.append(line)
    return out[:4]


def _reference_image_url(profile: Optional[dict]) -> Optional[str]:
    """The scraped photographic hero image (profile.visual.hero_image_url), used as
    the Veo image-to-video seed. Photo-only (logos are excluded upstream). A cheap
    scheme check here keeps this hermetic; the real SSRF/DNS guard runs at fetch
    time in the video provider (same discipline as the poster logo fetch)."""
    visual = (profile or {}).get("visual") or {}
    src = (visual.get("hero_image_url") or "").strip() if isinstance(visual, dict) else ""
    return src if src.startswith(("http://", "https://")) else None


def _content_images(profile: Optional[dict]) -> list[str]:
    """The brand's real on-page photos (profile.visual.content_images), logos
    excluded upstream. The faithful Ken Burns reel animates these."""
    visual = (profile or {}).get("visual") or {}
    if not isinstance(visual, dict):
        return []
    out = []
    for s in (visual.get("content_images") or []):
        s = (s or "").strip()
        if s.startswith(("http://", "https://")):
            out.append(s)
    return out[:12]


def _fit_durations(scenes: list[ReelScene], max_total_s: float) -> None:
    """Scale durations to fit `max_total_s`; if the per-scene minimum makes scaling
    overshoot, drop the lowest-priority OPTIONAL scene and rescale."""
    def total() -> float:
        return round(sum(s.duration_s for s in scenes), 2)

    while total() > max_total_s and len(scenes) > 2:
        factor = max_total_s / total()
        floored = False
        for s in scenes:
            scaled = s.duration_s * factor
            if scaled < _MIN_SCENE_S:
                scaled = _MIN_SCENE_S
                floored = True
            s.duration_s = round(scaled, 2)
        if total() <= max_total_s or not floored:
            break
        for kind in _DROP_PRIORITY:
            idx = next((i for i, s in enumerate(scenes) if s.kind == kind), None)
            if idx is not None:
                scenes.pop(idx)
                break
        else:
            break


def build_storyboard(
    brief: PosterBrief, *, profile: Optional[dict] = None, caller: Optional[Any] = None,
    max_total_s: float = 20.0,
) -> Storyboard:
    """Compose the ordered, length-capped scene list. `profile` (the serialized
    BusinessProfile) grounds the footage; `caller` (an OpenAI caller) enables the
    LLM art-director so the scene is DERIVED from the brand's persona — one call per
    reel, shared by all scenes — falling back to deterministic templates when absent.
    The contact scene uses the clean phone/email."""
    primary_dir = "rtl" if (is_rtl(brief.headline) or is_rtl(brief.business_name)) else "ltr"
    # One LLM art-director call per reel (shared across scenes); None -> templates.
    base_scene = build_brand_scene(brief, profile, caller)
    scenes: list[ReelScene] = []

    def vp(kind: str) -> str:
        return build_scene_prompt(kind, brief, profile=profile, base_scene=base_scene)

    # 1) Intro — strongest verbatim brand line (always present).
    scenes.append(ReelScene(
        kind="intro", duration_s=_INTRO_S, visual_prompt=vp("intro"),
        headline=brief.headline, source_field="headline",
    ))

    # 2) Offerings — verbatim names, stacked (skipped when none).
    if brief.offerings:
        items = brief.offerings[:3]
        scenes.append(ReelScene(
            kind="offering",
            duration_s=round(_OFFERING_BASE_S + _OFFERING_PER_ITEM_S * len(items), 2),
            visual_prompt=vp("offering"), sublines=items, source_field="offerings",
        ))

    # 3) Value prop — description sentence, when distinct from the headline.
    if brief.subheadline and brief.subheadline.strip() and brief.subheadline != brief.headline:
        scenes.append(ReelScene(
            kind="value_prop", duration_s=_VALUE_S, visual_prompt=vp("value_prop"),
            sublines=[brief.subheadline], source_field="subheadline",
        ))

    # 4) Contact — phone first, then email + socials (skipped when none).
    contact_lines = _contact_lines(brief, profile)
    if contact_lines:
        scenes.append(ReelScene(
            kind="contact", duration_s=_CONTACT_S, visual_prompt=vp("contact"),
            sublines=contact_lines, source_field="contact_channels/social",
        ))

    # 5) Outro — brand name + the REAL scraped CTA (always present).
    scenes.append(ReelScene(
        kind="outro", duration_s=_OUTRO_S, visual_prompt=vp("outro"),
        headline=brief.business_name, cta_text=brief.cta_text, source_field="name/cta",
    ))

    _fit_durations(scenes, max_total_s)

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
        reference_image_url=_reference_image_url(profile),
        content_images=_content_images(profile),
        warnings=list(brief.warnings),
    )
