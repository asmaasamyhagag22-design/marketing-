"""Art director: turn the profile's REAL signals (name, category, description,
offerings, audience, tone, languages) into a rich, text-free Veo prompt per scene
— footage of people and places that match THIS business's actual identity.

Discipline (same as the poster's art director):
  * The VISUAL is evocative, on-brand b-roll steered by the scraped signals. It
    carries MOOD, not factual claims — facts live in the verbatim text overlay.
  * Strictly TEXT-FREE (Veo garbles baked text); reserves space for the overlay.
  * GROUNDED IN IDENTITY: a restaurant's cuisine/region is read from its own name +
    description + offerings (e.g. "Qasr Elkbabgi" + "Eastern" -> Egyptian/oriental
    grill, NOT generic Western fine-dining). We never invent a cuisine that isn't
    signalled by the brand's real text.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from poster.schemas import PosterBrief

# Cuisine/region signals (in the brand's OWN name/description/offerings) ->
# authentic Middle Eastern / Egyptian oriental footage instead of generic Western.
_ORIENTAL_TOKENS = (
    "kebab", "kbab", "kabab", "kbabgi", "kebabgi", "grill", "grilled", "mashwi",
    "mashawi", "mishwi", "shawarma", "shawerma", "shish", "mezze", "meze", "kofta",
    "oriental", "eastern", "egyptian", "egypt", "arabic", "arab", "lebanese",
    "syrian", "levantine", "koshary", "kushari", "tagine", "hummus", "falafel",
    "mandi", "middle eastern", "مشوي", "مشاوي", "كباب", "مشويات", "شرقي", "مصري",
)

# Regional/cultural signals — NO food words. Used ONLY to add an Egyptian /
# Middle Eastern people-and-setting cue for ANY vertical (education, clinic, ...)
# without implying a restaurant. Keeping these separate from _ORIENTAL_TOKENS is
# what stops "food" leaking into a Digilians/NTI education reel.
_MENA_TOKENS = (
    "egypt", "egyptian", "arabic", "arab", "oriental", "eastern", "middle eastern",
    "lebanese", "syrian", "levantine", "gulf", "saudi", "emirati",
    "مصر", "مصري", "مصرية", "عربي", "عربية", "شرقي", "الشرق",
)

_VERTICAL_SCENE = {
    "cafe": "a cozy specialty cafe — a barista crafting coffee, friends chatting over "
            "cups at warm wooden tables, morning light",
    "education": "a bright modern learning space — diverse young adults collaborating on "
                 "laptops, an instructor guiding a small group, screens of code, aspirational energy",
    "medical_clinic": "a clean reassuring modern clinic — a friendly doctor talking with a "
                      "patient, soft daylight, calm and professional",
    "clinic": "a clean reassuring modern clinic — a friendly clinician with a patient, soft daylight, calm",
    "skincare": "a serene beauty setting — radiant glowing skin in soft diffused light, "
                "elegant product textures, premium and clean",
    "beauty": "an elegant beauty studio — a confident client, soft light, refined premium mood",
    "retail": "a stylish retail space — shoppers browsing beautifully arranged products, bright and modern",
    "ecommerce": "lifestyle product moments — hands interacting with desirable products, clean bright styling",
    "fitness": "an energetic modern gym — people training with focus and momentum, dynamic light",
    "real_estate": "elegant modern interiors and architecture — people viewing bright, beautifully staged spaces",
}
_DEFAULT_SCENE = ("a professional modern workplace — a confident, collaborative team in a "
                  "bright clean space, purposeful energy")

# Camera beats — category-NEUTRAL on purpose. They must NOT contain restaurant/
# hospitality words ("food", "guests", "hospitable"): those leaked into EVERY
# vertical (a Digilians/NTI education reel got "food" from the offering/value/
# contact beats). Food belongs only in _restaurant_scene, never here.
_BEAT = {
    "intro": "Establishing wide shot, slow cinematic push-in that reveals the scene.",
    "offering": "Smooth gimbal medium shots showcasing the offering/subject up close, people engaging with it.",
    "value_prop": "Intimate shot on a person's genuine reaction and a meaningful detail, gentle slow motion.",
    "contact": "Warm welcoming shot — people connecting, inviting and approachable.",
    "outro": "Hero brand moment, slow elegant pull-back with a soft warm glow.",
}

_TEXT_FREE = (
    "Absolutely NO text, words, letters, numbers, logos, watermarks, or signage anywhere. "
    "Leave calm, clean negative space (center and lower third) for text added later. "
    "Vertical 9:16 framing, cinematic photoreal footage, natural lighting, shallow depth of "
    "field, gentle authentic motion. No on-screen captions."
)


def _field(profile: Optional[dict], key: str) -> str:
    if not profile:
        return ""
    v = profile.get(key)
    if isinstance(v, dict):
        v = v.get("value")
    return str(v).strip() if v else ""


def _ground_text(brief: PosterBrief, profile: Optional[dict]) -> str:
    """All the brand's own descriptive text, for cuisine/identity detection."""
    parts = [brief.business_name or "", brief.headline or "", brief.subheadline or "",
             _field(profile, "description"), _field(profile, "tagline")]
    for o in ((profile or {}).get("offerings") or []):
        if isinstance(o, dict) and o.get("name"):
            parts.append(str(o["name"]))
    return " ".join(p for p in parts if p).lower()


def _restaurant_scene(ground: str) -> str:
    """Pick restaurant footage that matches the brand's real cuisine signals."""
    if any(tok in ground for tok in _ORIENTAL_TOKENS):
        return ("an authentic Egyptian / Middle Eastern restaurant — sizzling charcoal-grilled "
                "kebabs, mixed grills and kofta, generous oriental mezze and traditional dishes "
                "on the table, warm hospitable atmosphere, local Egyptian guests sharing the meal, "
                "oriental lanterns and traditional decor, NOT generic Western fine-dining")
    return ("an authentic local restaurant serving its signature dishes, warm welcoming "
            "atmosphere, real guests enjoying a shared meal, culturally true to the brand")


def _scene_base(brief: PosterBrief, ground: str) -> str:
    cat = (brief.category or "").lower()
    if "restaurant" in cat or "cafe" in cat:
        # Cafe only if explicitly a cafe AND no strong food/grill signal.
        if "cafe" in cat and not any(t in ground for t in _ORIENTAL_TOKENS):
            return _VERTICAL_SCENE["cafe"]
        return _restaurant_scene(ground)
    for key, scene in _VERTICAL_SCENE.items():
        if key in cat:
            return scene
    return _DEFAULT_SCENE


class _BrandSceneResponse(BaseModel):
    scene: str


def build_brand_scene(
    brief: PosterBrief, profile: Optional[dict], caller: Optional[Any]
) -> Optional[str]:
    """LLM art-director for the reel: invent ONE text-free, on-brand b-roll SCENE
    derived from the brand's VERBATIM persona — so two brands in the same category
    get DIFFERENT, identity-true footage instead of a fixed category template.

    Returns None when no caller is given or the call fails (the caller then falls
    back to the deterministic _scene_base). The scene is purely VISUAL (no factual
    claims) and TEXT-FREE (all words are overlaid later). Mirrors the poster's
    build_llm_concept_prompt discipline; reuses its _persona_lines block.
    """
    if caller is None:
        return None
    try:
        from poster.art_director import _persona_lines
        persona = _persona_lines(profile)
    except Exception:
        persona = ""
    ground = _ground_text(brief, profile)
    langs = [str(l).lower()[:2] for l in ((profile or {}).get("languages") or [])]
    is_mena = ("ar" in langs) or any(t in ground for t in _MENA_TOKENS)
    culture = ("The brand is Egyptian / Middle Eastern: depict authentic regional people and "
               "setting, culturally accurate, no clichés. " if is_mena else "")
    system = (
        "You are an award-winning art director for premium vertical (9:16) marketing REELS. "
        "Invent ONE photoreal, TEXT-FREE b-roll scene for THIS specific brand: the setting, the "
        "people, and the action/mood that authentically show what this business does and who it "
        "serves. Derive EVERYTHING from the brand persona provided — never a generic category "
        "template. " + culture +
        "Describe ONLY the visual scene (people, place, action, light, mood). ABSOLUTELY NO text, "
        "words, letters, numbers, logos, or signage. Cinematic, natural light, shallow depth of "
        "field, gentle motion, with calm negative space for text overlaid later. 1-2 sentences."
    )
    user = (
        f"Business: {brief.business_name}\n"
        f"Category: {brief.category}\n"
        f"Real offerings: {'; '.join([o for o in (brief.offerings or [])[:5] if o]) or (brief.category or '')}\n"
        f"Tone: {brief.tone or 'premium'}\n"
        + (f"\nBrand persona (verbatim from the real website):\n{persona}\n" if persona else "")
        + "\nReturn a single vivid, text-free 'scene' description for this brand."
    )
    try:
        resp, _usage = caller(system, user, _BrandSceneResponse, group_name="reel_scene")
        scene = (getattr(resp, "scene", "") or "").strip()
        return scene or None
    except Exception:
        return None


def build_scene_prompt(
    scene_kind: str, brief: PosterBrief, *, profile: Optional[dict] = None,
    base_scene: Optional[str] = None,
) -> str:
    """A complete, text-free Veo prompt: on-identity people + place, brand color
    grade, culturally accurate, with room for the overlay. When `base_scene` is
    supplied (from the LLM art-director) it drives the scene; otherwise a
    deterministic per-category template is the fallback."""
    ground = _ground_text(brief, profile)
    base = base_scene or _scene_base(brief, ground)
    beat = _BEAT.get(scene_kind, _BEAT["intro"])
    # Lead the color grade with the REAL primary brand color (not an unordered
    # swatch list), so the brand's signature hue actually drives the scene.
    primary = brief.primary_color or (brief.palette_hex[0] if brief.palette_hex else "")
    others = ", ".join(c for c in brief.palette_hex[:4] if c != primary)
    color_cue = (
        f"Lead the cinematic color grade with the brand's primary color {primary}"
        + (f", supported by {others}" if others else "") + ". "
    ) if primary else ""
    tone = (brief.tone or "").strip().lower()
    tone_phrase = f"{tone} mood, " if tone else ""

    languages = [str(l).lower()[:2] for l in ((profile or {}).get("languages") or [])]
    # Regional cue ONLY (no food) — so an Egyptian education/clinic brand gets
    # Egyptian PEOPLE + setting, never food. Food lives only in the restaurant base.
    is_mena = ("ar" in languages) or any(t in ground for t in _MENA_TOKENS)
    culture = ("Authentic Egyptian / Middle Eastern people and setting, culturally accurate. "
               if is_mena else "Culturally authentic to the brand. ")

    return (
        f"{beat} Scene: {base}. {culture}{tone_phrase}{color_cue}"
        f"Premium, modern, documentary-real for the brand '{brief.business_name}'. {_TEXT_FREE}"
    )
