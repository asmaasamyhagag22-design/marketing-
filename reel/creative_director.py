"""Opus creative director for the reel.

The user wants more than "animate a photo + stamp static text". They want a real
creative DIRECTOR: send the business identity + the REAL photos to Claude Opus, and
let it design a complete, engaging reel — for EACH scene a rich Veo 3.1
image-to-video prompt (cinematic MOTION and life inside the scene: people moving,
ambient action, camera movement — not just a zoom), a punchy VOICE-OVER line, and
an optional short on-screen caption — opening with a scroll-stopping hook, built to
earn likes/shares and convert viewers into customers.

Opus SEES the real photos (vision), so each scene's motion is true to what's
actually in that photo. Discipline: the VISUALS stay real (real photos) and no
factual claim may be invented (no fake awards/numbers/certifications) — but the copy
is allowed to be persuasive and evocative, grounded in the provided identity.

No key / SDK -> None (honest-degrade), never raises.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-opus-4-8"


class CreativeScene(BaseModel):
    image_index: int                       # which real photo to bring to life
    veo_prompt: str                        # rich image-to-video prompt for Veo 3.1
    voiceover: str = ""                     # narration line (brand language)
    voiceover_delivery: str = ""           # emotion/performance note for this line
    on_screen_text: str = ""               # short kinetic caption (may be empty)
    duration_s: float = 4.0


class CreativeReel(BaseModel):
    concept: str = ""                       # the creative idea in one line
    hook: str = ""                          # scroll-stopping opener
    music_mood: str = ""                    # suggested soundtrack vibe
    cta: str = ""                           # closing call to action (verbatim from brand if possible)
    language: str = "en"
    images: list[str] = Field(default_factory=list)   # the real photos Opus saw, in index order
    scenes: list[CreativeScene] = Field(default_factory=list)
    model: str = _DEFAULT_MODEL


def _v(profile: dict, key: str) -> str:
    f = profile.get(key)
    if isinstance(f, dict):
        f = f.get("value")
    return str(f).strip() if f else ""


def _identity_block(profile: dict) -> str:
    """A compact identity brief for Opus — reuses the domain-adaptive schema when
    available so the director understands THIS vertical, not a generic one."""
    lines = [f"Business: {_v(profile, 'name')}"]
    for k, lbl in (("category", "Category"), ("tagline", "Tagline"),
                   ("description", "About"), ("audience_type", "Audience"),
                   ("tone_of_voice", "Tone"), ("pricing_posture", "Pricing")):
        val = _v(profile, k)
        if val:
            lines.append(f"{lbl}: {val}")
    offerings = [o.get("name") for o in (profile.get("offerings") or []) if isinstance(o, dict) and o.get("name")]
    if offerings:
        lines.append("Offerings: " + "; ".join(offerings))
    vps = [(x.get("value") if isinstance(x, dict) else x) for x in (profile.get("value_propositions") or [])]
    vps = [str(v).strip() for v in vps if v]
    if vps:
        lines.append("Value props: " + "; ".join(vps))

    # Domain-adaptive attributes (Claude-generated, grounded) — the richest signal.
    try:
        from business_profile.domain_schema import build_domain_profile
        dp = build_domain_profile(profile)
        if dp:
            lines.append(f"Specific vertical: {dp.vertical}")
            for f in dp.fields:
                lines.append(f"- {f.label}: {f.value}")
    except Exception:
        pass
    return "\n".join(lines)


def _image_blocks(image_urls: list[str], *, max_images: int, max_side: int = 640) -> tuple[list[dict], list[str]]:
    """Download + downscale each real photo to an Anthropic image block. Returns
    (blocks, used_urls) — only the images we could actually fetch, in order."""
    import base64
    import io
    from reel.video_provider import _load_reference_image
    blocks: list[dict] = []
    used: list[str] = []
    for u in image_urls[:max_images]:
        loaded = _load_reference_image(u)
        if not loaded:
            continue
        data, _mime = loaded
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82)
            data = buf.getvalue()
        except Exception:
            pass
        blocks.append({"type": "text", "text": f"REAL PHOTO index {len(used)}:"})
        blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": base64.b64encode(data).decode("ascii")},
        })
        used.append(u)
    return blocks, used


# Vertical/tone modes. The old single prompt hard-coded FOOD dynamics ("steam/smoke, flames,
# mouth-watering excitement") into every reel — wrong for a jewelry house or a clinic. The motion
# vocabulary, delivery examples, and imagery now swap by mode so each reel is true to its brand.
_ELEGANT_CATS = {"jewelry", "jewellery", "fashion", "accessories", "watches", "couture"}
_FOOD_CATS = {"restaurant", "cafe", "bakery", "food", "fast_food", "patisserie", "coffee_shop"}
_BEAUTY_CATS = {"beauty", "cosmetics", "cosmetic", "skincare", "haircare", "salon", "spa", "personal_care"}
_BEAUTY_KEYWORDS = ("skin", "hair", "face", "lip", "cosmetic", "cream", "serum", "cleanser", "mist",
                    " oil", "shampoo", "makeup", "lotion", "beauty", "salon", "fragrance", "perfume")


def _is_beauty(profile: dict) -> bool:
    """A beauty/skincare/haircare brand — often typed just 'ecommerce', so detect it from the
    offerings/description keywords (>=2 hits). This vertical is the MOST people-driven (someone
    applying the product), so it must not fall into the bland 'generic' motion."""
    text = (_v(profile, "description") + " " + _v(profile, "tagline") + " " + " ".join(
        str(o.get("name") if isinstance(o, dict) else o) for o in (profile.get("offerings") or []))).lower()
    return sum(1 for k in _BEAUTY_KEYWORDS if k in text) >= 2


def _vertical_mode(profile: dict) -> str:
    """'beauty' (person applying the product), 'elegant' (luxury/jewelry, worn), 'food' (savoured),
    else 'generic' — every mode now demands a PERSON using the product with real energy."""
    cat = _v(profile, "category").lower()
    tone = _v(profile, "tone_of_voice").lower()
    if cat in _BEAUTY_CATS or _is_beauty(profile):
        return "beauty"
    if tone == "luxury" or cat in _ELEGANT_CATS:
        return "elegant"
    if cat in _FOOD_CATS:
        return "food"
    return "generic"


# Shared rule for EVERY mode: a real PERSON enters frame and USES the product, energetic/TikTok-native
# motion — the OLD guidance ("refined", "never spectacle", "slow push-in", "true to that exact photo")
# made Veo only move the camera over a still, which read as a static zoom (owner: "الصورة متزومة
# مبتهزش"). The PRODUCT stays exactly as shown (it's the i2v seed); only the person/action is generated.
_MOTION_TAIL = (" The PRODUCT in the photo must stay exactly as shown (same shape, label, colour); ADD "
                "the person and the action AROUND it. Show only PHYSICALLY LOGICAL use — if the product "
                "has a cap / lid / pump / dropper, the person REMOVES or FLIPS it BEFORE dispensing, and "
                "operates it the way it really works; NEVER an impossible action (pressing a sealed pump, "
                "pouring from a closed bottle). Real, energetic movement in every second — NOT a slow "
                "zoom, NOT a static pan. Add no fake text, logos, or signage.")
_MOTION_GUIDANCE = {
    "beauty": (
        "- veo_prompt: a vivid, TikTok-native Veo 3.1 IMAGE-TO-VIDEO prompt where a real PERSON uses "
        "THIS exact product: a hand enters frame, picks it up and applies it (sprays the mist into "
        "flowing hair, smooths the oil through strands, works the cleanser on fresh skin), and the "
        "model REACTS — a satisfied smile, hair catching the light and swinging, glowing skin. "
        "Tactile, quick natural gestures, a snappy push-in or whip-pan." + _MOTION_TAIL
    ),
    "elegant": (
        "- veo_prompt: a vivid Veo 3.1 IMAGE-TO-VIDEO prompt where a poised model WEARS/holds THIS "
        "exact piece and it comes ALIVE — a hand turning it into the light, the piece on skin as she "
        "moves, an admiring glance, fabric and light shifting, a confident dynamic camera. Refined "
        "but ALIVE, real movement." + _MOTION_TAIL
    ),
    "food": (
        "- veo_prompt: a vivid Veo 3.1 IMAGE-TO-VIDEO prompt where a real person ENJOYS this exact "
        "dish — a hand reaches in and lifts/pours/plates it, a satisfied bite, rising steam, sauce "
        "glistening, energetic appetite-driven motion." + _MOTION_TAIL
    ),
    "generic": (
        "- veo_prompt: a vivid Veo 3.1 IMAGE-TO-VIDEO prompt where a real PERSON picks up and USES "
        "this exact product and reacts genuinely — hands working, natural gestures, a dynamic camera "
        "with real energy and life." + _MOTION_TAIL
    ),
}
_DELIVERY_EG = {
    "beauty": "'fresh and upbeat', 'confident glow', 'delighted reaction', 'warm friendly invitation'",
    "elegant": "'hushed reverence', 'quiet confidence', 'warm elegant invitation', 'proud heritage'",
    "food": "'intrigued, slow build', 'mouth-watering excitement', 'warm proud invitation'",
    "generic": "'confident and bold', 'upbeat and energetic', 'warm proud invitation'",
}


def _system_prompt(n_scenes: int, language: str, mode: str = "generic",
                   featured: Optional[str] = None) -> str:
    motion = _MOTION_GUIDANCE.get(mode, _MOTION_GUIDANCE["generic"])
    deliveries = _DELIVERY_EG.get(mode, _DELIVERY_EG["generic"])
    if featured:                     # ONE picked product: several SHOTS of the SAME item
        featured_line = (
            f"FEATURED PRODUCT: {featured}. This reel advertises ONLY this product — EVERY scene is "
            "the SAME product (REAL PHOTO index 0), varied by SHOT and ACTION (macro detail, in-hand "
            "pickup, real in-use application, satisfied result), NEVER a different product.\n\n")
        image_rule = "- image_index: ALWAYS 0 — the SAME featured product; vary the shot/action, not the product.\n"
        seq_rule = ("Anchor EVERY scene on the ONE featured product (index 0); vary the SHOT and the "
                    "ACTION, not the item — a fast sequence of different angles/uses of the SAME product.")
        check_seq = "on the SAME featured product with varied shots"
    else:                            # whole-brand: a distinct product per scene
        featured_line = ""
        image_rule = "- image_index: which REAL photo to bring to life (a DIFFERENT one per scene).\n"
        seq_rule = ("Use a DISTINCT photo for each scene (different image_index) so it's a fast SEQUENCE "
                    "of shots, not one image lingering.")
        check_seq = "on DISTINCT photos"
    framing = (
        "FRAMING: you compose for a 1080x1920 VERTICAL (9:16) frame. Compose vertical-first — the "
        "product FULLY visible with headroom and safe margins, centered or in the lower two-thirds "
        "with negative space above for motion/text. NEVER a wide/landscape shot that gets cropped; "
        "the seed photo is often square/portrait, so place it so NOTHING is cut off.\n\n")
    return (
        "You are a world-class short-form video CREATIVE DIRECTOR (think top TikTok/Reels "
        "ad agency). You design vertical 9:16 marketing reels that stop the scroll, earn "
        "likes and shares, and make viewers want to BUY / book / enrol.\n\n"
        + featured_line
        + "You are given a business's identity and its REAL photos (you can see them). Design a "
        f"{n_scenes}-scene reel that ADVERTISES this brand with a clear AD SPINE the scenes MUST "
        "follow in order: (1) HOOK — scene 0 shows the product/brand and stops the scroll; (2) WHAT "
        "IT IS — name the brand and the hero product/offering; (3) BENEFIT — the core reason to buy, "
        "drawn ONLY from the identity (value props / offerings); (4) PROOF or differentiator, if "
        "grounded; (5) CTA — verbatim from the brand.\n"
        "HARD RULE: by scene 2 a first-time viewer must know exactly WHAT BRAND and WHAT PRODUCT this "
        "advertises — if not, the reel has FAILED. Anchor the WHOLE reel on ONE concrete hero product/"
        "offering (the product in REAL PHOTO index 0 when one is featured); do NOT narrate store "
        "locations, kiosks, branches, or a vague brand montage. If the identity signals HERITAGE, "
        "weave that in — never invent history.\n\n"
        + framing
        + "MOTION & PEOPLE (this is a TikTok-style ad, not a slideshow): EVERY scene must have real,"
        " energetic MOTION and — wherever the product is used or worn — a real PERSON in frame using"
        " or reacting to it. NEVER a slow zoom or a static pan over a still. " + seq_rule + "\n\n"
        "For EACH scene:\n"
        + image_rule
        + motion + "\n"
        f"- voiceover: one short, natural narration line in {language} that carries the story and "
        "sells the moment.\n"
        "- voiceover_delivery: the EMOTION/performance for that line in a few words "
        f"(e.g. {deliveries}) — vary it across scenes so the read has real feeling.\n"
        "- on_screen_text: keep the reel almost TEXT-FREE — the visuals and voice-over carry it. "
        "EXCEPT scene 0: its caption MUST name the brand or the featured product/category, so even a "
        "MUTED viewer instantly knows what this advertises. Optionally a 2-4 word CTA caption on the "
        'LAST scene; leave on_screen_text EMPTY ("") for every other scene.\n'
        "- duration_s: 3-6.\n\n"
        "DISCIPLINE: be creative and persuasive, but invent NO facts — no fake awards, ratings, "
        "numbers, or certifications. Every factual claim must come from the identity provided. "
        "The reel must feel premium, human, and authentic to THIS brand's vertical.\n"
        "SELF-CHECK before returning: the reel NAMES the brand, NAMES/SHOWS one hero product, states "
        ">=1 real benefit, ends on the CTA — using ONLY identity facts — AND most scenes show a real "
        "PERSON using/reacting to the product with visible motion (not a camera move over a still) "
        + check_seq + ". If any is missing, rewrite it.\n\n"
        "Return ONLY a JSON object, no prose, no markdown fences:\n"
        '{"concept":"...","hook":"...","music_mood":"...","cta":"...","language":"' + language + '",'
        '"scenes":[{"image_index":0,"veo_prompt":"...","voiceover":"...","voiceover_delivery":"...",'
        '"on_screen_text":"...","duration_s":4}]}'
    )


def design_creative_reel(
    profile: dict,
    image_urls: list[str],
    *,
    n_scenes: int = 6,
    language: Optional[str] = None,
    featured_product: Optional[str] = None,
    api_key: Optional[str] = None,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 2500,
) -> Optional[CreativeReel]:
    """Opus designs the full creative reel from the identity + real photos. When `featured_product`
    is set, the WHOLE reel is about that ONE product (several shots of the same item). Returns None
    on any failure (no key/SDK/images/parse)."""
    urls = [u for u in (image_urls or []) if isinstance(u, str) and u.startswith(("http://", "https://"))]
    if not urls:
        logger.info("creative_director: no real photos; skipping")
        return None
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        logger.info("creative_director: ANTHROPIC_API_KEY not set; skipping")
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning("creative_director: anthropic SDK not installed")
        return None

    langs = profile.get("languages") or []
    lang = language or (str(langs[0]) if langs else "en")

    blocks, used = _image_blocks(urls, max_images=n_scenes + 4)
    if not blocks:
        logger.warning("creative_director: could not fetch any real photo")
        return None

    feat = (f"\n\nFEATURED PRODUCT (advertise ONLY this): {featured_product}. Every scene is the SAME "
            "product below — vary the shot/action, not the item." if featured_product else "")
    content = [{"type": "text", "text":
                "BUSINESS IDENTITY:\n" + _identity_block(profile) + feat +
                f"\n\nYou have {len(used)} real photos below. Design the reel."}]
    content.extend(blocks)

    try:
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=model, max_tokens=max_tokens,
            system=_system_prompt(n_scenes, lang, _vertical_mode(profile), featured=featured_product),
            messages=[{"role": "user", "content": content}],
        )
        raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    except Exception as e:  # noqa: BLE001
        logger.warning("creative_director: Opus call failed: %s", e)
        return None

    data = _safe_json_object(raw)
    if not data:
        return None
    scenes: list[CreativeScene] = []
    for s in (data.get("scenes") or []):
        if not isinstance(s, dict):
            continue
        try:
            idx = int(s.get("image_index", 0))
        except (TypeError, ValueError):
            idx = 0
        idx = max(0, min(idx, len(used) - 1))
        prompt = str(s.get("veo_prompt", "")).strip()
        if not prompt:
            continue
        scenes.append(CreativeScene(
            image_index=idx, veo_prompt=prompt,
            voiceover=str(s.get("voiceover", "")).strip(),
            voiceover_delivery=str(s.get("voiceover_delivery", "")).strip(),
            on_screen_text=str(s.get("on_screen_text", "")).strip(),
            duration_s=float(s.get("duration_s", 4.0) or 4.0),
        ))
    if not scenes:
        return None
    return CreativeReel(
        concept=str(data.get("concept", "")).strip(),
        hook=str(data.get("hook", "")).strip(),
        music_mood=str(data.get("music_mood", "")).strip(),
        cta=str(data.get("cta", "")).strip(),
        language=lang, images=used, scenes=scenes, model=model,
    )


def _safe_json_object(raw: str):
    if not raw:
        return None
    s = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        s = s[start:end + 1]
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None
