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
_GALLERY_S = 2.6                # pure animated-real-photo b-roll shot

_MIN_SCENE_S = 1.5

# Drop order when over the length cap (intro + outro are never dropped). Gallery
# b-roll is the first to go — it's the "extra" the photo pool lets us add.
_DROP_PRIORITY = ["gallery", "value_prop", "contact", "offering"]


def _i2v_motion_prompt(brief: PosterBrief) -> str:
    """The prompt for a scene SEEDED from a real photo. It steers MOTION only and
    forbids changing the scene — so Veo 3.1 brings the REAL photo to life (a gentle
    camera move + ambient motion) instead of inventing a new place. The seed photo
    IS the content; the prompt must not fight it."""
    tone = (brief.tone or "premium").strip().lower()
    return (
        f"Bring this real photograph of {brief.business_name} to life with subtle, "
        "natural, photorealistic motion: a gentle slow camera push-in or drift, soft "
        "ambient movement (rising steam, flickering warm light, slight motion of "
        "people, hands, and fabric), shallow depth of field. KEEP the real scene, "
        "people, food, setting, and colors EXACTLY as in the image — do NOT add, "
        "remove, replace, or restyle any object, and add NO text, words, or signage. "
        f"Cinematic, {tone}, documentary-real, vertical 9:16."
    )


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
    max_total_s: float = 28.0, target_scenes: int = 10,
    selected_images: Optional[list[str]] = None,
) -> Storyboard:
    """Compose the ordered, length-capped scene list. `profile` (the serialized
    BusinessProfile) grounds the footage; `caller` (an OpenAI caller) enables the
    LLM art-director so a TEXT-TO-VIDEO fallback scene is DERIVED from the brand's
    persona. When the scrape has real photos, EACH scene is SEEDED from one (cycling
    through `content_images`) — Veo 3.1 then animates the real place and `gallery`
    b-roll scenes fill up to `target_scenes` so it reads as a real reel, not a
    static slideshow. The contact scene uses the clean phone/email."""
    primary_dir = "rtl" if (is_rtl(brief.headline) or is_rtl(brief.business_name)) else "ltr"
    # One LLM art-director call per reel — only used for the no-seed (text-to-video)
    # fallback prompt; seeded scenes use the faithful motion prompt instead.
    base_scene = build_brand_scene(brief, profile, caller)
    # `selected_images` (vision-curated real photos) overrides the raw content set
    # when provided — so logos/QR/partner badges never become scenes. None means
    # "not curated"; fall back to the profile's content_images.
    content = selected_images if selected_images is not None else _content_images(profile)

    # ---- ordered scene SPECS (text + kind + duration), outro held until the end ----
    specs: list[dict] = [dict(kind="intro", duration_s=_INTRO_S,
                              headline=brief.headline, source_field="headline")]
    if brief.offerings:
        items = brief.offerings[:3]
        specs.append(dict(
            kind="offering",
            duration_s=round(_OFFERING_BASE_S + _OFFERING_PER_ITEM_S * len(items), 2),
            sublines=items, source_field="offerings"))
    if brief.subheadline and brief.subheadline.strip() and brief.subheadline != brief.headline:
        specs.append(dict(kind="value_prop", duration_s=_VALUE_S,
                          sublines=[brief.subheadline], source_field="subheadline"))
    contact_lines = _contact_lines(brief, profile)
    if contact_lines:
        specs.append(dict(kind="contact", duration_s=_CONTACT_S,
                          sublines=contact_lines, source_field="contact_channels/social"))
    outro_spec = dict(kind="outro", duration_s=_OUTRO_S,
                      headline=brief.business_name, cta_text=brief.cta_text,
                      source_field="name/cta")

    # ---- gallery b-roll: only when we have real photos to animate. Fill up to
    # target_scenes (incl. outro), bounded so we don't make more gallery shots than
    # there are distinct unused photos (avoids the same photo twice back-to-back).
    n_with_outro = len(specs) + 1
    if content:
        n_gallery = max(0, min(target_scenes - n_with_outro, len(content) - n_with_outro))
        for _ in range(n_gallery):
            specs.append(dict(kind="gallery", duration_s=_GALLERY_S, source_field="content_image"))
    specs.append(outro_spec)

    # ---- assign a real-photo SEED + the right prompt to each scene ----
    scenes: list[ReelScene] = []
    for i, spec in enumerate(specs):
        seed = content[i % len(content)] if content else None
        if seed:
            prompt = _i2v_motion_prompt(brief)          # animate the REAL photo
        else:
            base_kind = spec["kind"] if spec["kind"] != "gallery" else "intro"
            prompt = build_scene_prompt(base_kind, brief, profile=profile, base_scene=base_scene)
        scenes.append(ReelScene(visual_prompt=prompt, seed_image_url=seed, **spec))

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
        content_images=list(content),   # the CURATED real-photo set actually used
        warnings=list(brief.warnings),
    )
