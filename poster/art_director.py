from __future__ import annotations

import random
from typing import Any, Optional

from pydantic import BaseModel

from poster.schemas import PosterArtDirection, PosterBrief


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _palette_text(colors: list[str]) -> str:
    if not colors:
        return "a professional brand palette"
    return ", ".join(colors[:5])


def _safe_overlay_copy(brief: PosterBrief) -> str:
    """
    Keep overlay copy short. The full profile description is too long for a poster.
    """
    parts: list[str] = []

    if brief.headline:
        parts.append(brief.headline)

    if brief.offerings:
        parts.append(brief.offerings[0])

    text = " • ".join(parts)
    if len(text) <= 105:
        return text

    return text[:102].rstrip(" ,.;:") + "..."


def _category_key(category: str | None) -> str:
    c = (category or "").lower()

    if "restaurant" in c or "cafe" in c:
        return "restaurant"

    if "education" in c or "training" in c or "institute" in c:
        return "education"

    if "medical" in c or "clinic" in c or "doctor" in c:
        return "medical"

    if "skincare" in c or "beauty" in c or "cosmetic" in c:
        return "skincare"

    return "business"


def _choose_layout(category: str) -> str:
    rng = random.SystemRandom()

    if category == "education":
        return rng.choice(
            [
                "clean_institutional",
                "split_editorial",
                "magazine_cover",
                "bottom_band",
            ]
        )

    if category == "restaurant":
        return rng.choice(
            [
                "hero_overlay",
                "magazine_cover",
                "bottom_band",
                "split_editorial",
            ]
        )

    if category == "medical":
        return rng.choice(
            [
                "split_editorial",
                "clean_institutional",
                "bottom_band",
            ]
        )

    if category == "skincare":
        return rng.choice(
            [
                "hero_overlay",
                "magazine_cover",
                "bottom_band",
            ]
        )

    return rng.choice(
        [
            "magazine_cover",
            "split_editorial",
            "bottom_band",
            "clean_institutional",
        ]
    )


def _layout_prompt(layout: str) -> str:
    if layout == "magazine_cover":
        return (
            "Composition strategy: premium magazine-cover style. "
            "Strong visual subject or atmosphere, dramatic depth, clear negative space around the center. "
            "Do not place busy objects where the main headline will be overlaid."
        )

    if layout == "split_editorial":
        return (
            "Composition strategy: editorial split layout. "
            "Place the main visual interest on one side and keep the opposite side cleaner for overlay text. "
            "Use premium campaign photography aesthetics."
        )

    if layout == "bottom_band":
        return (
            "Composition strategy: image-led poster with a clean lower-third area. "
            "Keep the top and middle visually rich, and leave the bottom area darker or calmer for CTA overlay."
        )

    if layout == "clean_institutional":
        return (
            "Composition strategy: clean institutional campaign layout. "
            "Use structured space, premium professional lighting, modern geometric depth, and clear overlay zones."
        )

    return (
        "Composition strategy: hero overlay. "
        "Create one strong visual scene with clear negative space for title, CTA, and logo."
    )


def build_art_direction(
    brief: PosterBrief,
    profile: dict[str, Any] | None = None,
) -> PosterArtDirection:
    """
    Build a creative direction from the scraped business profile.

    OpenAI generates background/scene only.
    Pillow overlays the exact logo, text, CTA, and contact.
    """
    category = _category_key(brief.category)
    layout = _choose_layout(category)

    palette = _palette_text(brief.palette_hex)
    offerings = ", ".join(brief.offerings[:3]) if brief.offerings else "core offerings"
    tone = brief.tone or "professional"
    brand = brief.business_name
    headline = brief.headline
    subheadline = brief.subheadline or ""

    layout_instruction = _layout_prompt(layout)

    source_fields = [
        "business_name",
        "category",
        "headline",
        "subheadline",
        "offerings",
        "palette_hex",
        "tone",
        "logo",
        "cta",
    ]

    if category == "restaurant":
        concept = "Premium restaurant campaign background"
        mood = "warm, appetizing, premium, hospitality-led"
        background_style = (
            "premium restaurant photography, authentic cuisine, elegant table atmosphere, "
            "cinematic lighting, realistic depth, refined hospitality"
        )
        category_prompt = f"""
Create a premium vertical marketing poster BACKGROUND for a restaurant brand.

Brand context:
- Brand name: {brand}
- Headline: {headline}
- Description: {subheadline}
- Offerings: {offerings}
- Tone: {tone}
- Brand palette: {palette}

Visual direction:
Show an elegant dining atmosphere with authentic cuisine, refined hospitality, and premium presentation.
Use appetizing lighting and brand-safe tones inspired by the palette.
Make it look like a real high-quality social media campaign visual.

{layout_instruction}

Strict rules:
No text. No words. No logo. No watermark. No readable menu. No price tags.
Do not generate typography or signage.
""".strip()

    elif category == "education":
        concept = "Modern education and career development campaign background"
        mood = "modern, credible, technology-oriented, aspirational"
        background_style = (
            "modern ICT learning environment, professional training, digital screens, "
            "career development, clean institutional design, realistic premium look"
        )
        category_prompt = f"""
Create a professional vertical marketing poster BACKGROUND for an education and training institute.

Brand context:
- Brand name: {brand}
- Headline: {headline}
- Description: {subheadline}
- Programs / offerings: {offerings}
- Tone: {tone}
- Brand palette: {palette}

Visual direction:
Show a modern technology-oriented learning environment.
Include subtle cues of ICT, networking, digital learning, certifications, training, and career growth.
The scene must feel premium, credible, institutional, and realistic.
Use a clean professional palette inspired by the brand colors.

{layout_instruction}

Strict rules:
No text. No words. No logo. No watermark. No fake certificate text. No readable signage.
Do not generate typography.
""".strip()

    elif category == "medical":
        concept = "Clean trustworthy healthcare campaign background"
        mood = "calm, clinical, trustworthy, reassuring"
        background_style = (
            "modern clinic interior, clean surfaces, soft natural light, professional healthcare atmosphere, "
            "subtle human warmth, no procedure scene"
        )
        category_prompt = f"""
Create a clean vertical marketing poster BACKGROUND for a medical clinic brand.

Brand context:
- Brand name: {brand}
- Headline: {headline}
- Services / offerings: {offerings}
- Tone: {tone}
- Brand palette: {palette}

Visual direction:
Show a modern clinic environment with a calm, trustworthy, professional atmosphere.
Use soft light, clean composition, and reassuring brand-safe colors.
The image should be suitable for compliant medical marketing and human review.

{layout_instruction}

Safety:
Do not show identifiable patients.
Do not show before/after imagery.
Do not show procedures, needles, blood, invasive treatment, or dramatic symptoms.
Do not imply guaranteed results.

Strict rules:
No text. No words. No logo. No watermark. No readable signage.
Do not generate typography.
""".strip()

    elif category == "skincare":
        concept = "Premium skincare campaign background"
        mood = "soft, clean, aspirational, ingredient-aware"
        background_style = (
            "premium skincare routine scene, soft light, clean surface, gentle cosmetic aesthetic, "
            "elegant product-like composition"
        )
        category_prompt = f"""
Create a premium vertical marketing poster BACKGROUND for a skincare or beauty brand.

Brand context:
- Brand name: {brand}
- Headline: {headline}
- Offerings: {offerings}
- Tone: {tone}
- Brand palette: {palette}

Visual direction:
Show a clean premium skincare routine scene with soft lighting, refined surfaces, elegant textures,
and aspirational but realistic beauty aesthetics.

{layout_instruction}

Compliance:
Do not imply medical treatment or guaranteed results.
Do not show skin disease, before/after comparisons, or clinical claims.

Strict rules:
No text. No words. No logo. No watermark. No readable labels.
Do not generate typography.
""".strip()

    else:
        concept = "Premium business campaign background"
        mood = "professional, modern, brand-led"
        background_style = (
            "premium abstract business campaign scene, modern brand visual, clean composition, "
            "elegant lighting and depth"
        )
        category_prompt = f"""
Create a premium vertical marketing poster BACKGROUND for a business brand.

Brand context:
- Brand name: {brand}
- Headline: {headline}
- Offerings: {offerings}
- Tone: {tone}
- Brand palette: {palette}

Visual direction:
Create a modern, professional, brand-safe campaign background with clean visual hierarchy.

{layout_instruction}

Strict rules:
No text. No words. No logo. No watermark. No readable signage.
Do not generate typography.
""".strip()

    negative_prompt = (
        "text, words, letters, typography, logo, watermark, readable signage, "
        "price tags, UI screens with readable words, fake certificates with text, "
        "distorted hands, distorted faces, low quality, blurry, cluttered layout, "
        "busy overlay zones, overexposed, cartoonish"
    )

    return PosterArtDirection(
        provider_prompt=category_prompt,
        negative_prompt=negative_prompt,
        concept=concept,
        category=category,
        mood=mood,
        layout=layout,  # type: ignore[arg-type]
        background_style=background_style,
        safe_overlay_copy=_safe_overlay_copy(brief),
        color_notes=[
            "Background is generated by OpenAI.",
            "Logo, business name, CTA, and contact are added by Pillow.",
            "Important text is never generated inside the image.",
            "Overlay layout is randomized per generation.",
        ],
        source_fields_used=source_fields,
    )


def build_creative_prompt(brief: PosterBrief, bake_text: bool = False) -> str:
    """Ultra-minimal, concept-driven advertising-poster prompt.

    Default (bake_text=False, RECOMMENDED): a TEXT-FREE creative concept with clean
    empty zones — the real logo + minimal copy are overlaid afterward (crisp, and
    Arabic-capable). bake_text=True asks the model to render the headline/CTA INSIDE
    the image; only viable for short English (it garbles Arabic and misspells text).
    Universal: the concept derives from the business's own category + hero offering,
    never a hardcoded vertical gag.
    """
    category = (brief.category or "brand").replace("_", " ")
    hero = brief.offerings[0] if brief.offerings else category
    palette = ", ".join(brief.palette_hex[:4]) or "a refined, premium brand palette"

    concept = f"""
A bold, ultra-minimal advertising poster for a {category} brand — ONE striking
creative concept, not a busy scene. Surreal forced-perspective with a single
dramatic hero subject inspired by "{hero}" as the focal point. Premium editorial /
high-fashion campaign aesthetic, vibrant yet clean, generous negative space,
cinematic studio lighting, soft shadows, photorealistic, magazine-quality, 8K.

Brand color palette: {palette}.""".strip()

    if bake_text:
        headline = _clean(brief.headline)
        cta = _clean(brief.cta_text)
        text_block = (
            "Typography baked into the image, rendered crisply and CORRECTLY, minimal "
            "and modern:\n"
            f'- a short headline reading exactly: "{headline}"\n'
            f'- a small pill call-to-action button reading exactly: "{cta}"\n'
            "Clean Latin typography only; no other words, captions, watermarks, or logos."
        )
    else:
        text_block = (
            "ABSOLUTELY NO text, words, letters, numbers, logos, captions, or signage "
            "anywhere in the image. Reserve a calm, empty band across the lower third "
            "(and a clean top corner) for a logo and a few words to be overlaid later."
        )

    return f"{concept}\n\n{text_block}\n\nVertical 4:5 poster, centered composition, advertising-campaign style."


class _CreativeConceptResponse(BaseModel):
    """Structured output from the LLM art-director."""
    concept_title: str
    image_prompt: str


def _profile_field_value(profile: dict[str, Any] | None, key: str) -> str:
    field = (profile or {}).get(key)
    if isinstance(field, dict):
        return _clean(field.get("value"))
    return _clean(field)


def _persona_lines(profile: dict[str, Any] | None) -> str:
    """Brand-persona block for the art-director — every line is verbatim scraped
    evidence from the profile (zero hallucination: omitted when absent)."""
    if not profile:
        return ""
    lines: list[str] = []
    tagline = _profile_field_value(profile, "tagline")
    if tagline:
        lines.append(f"- Tagline (verbatim): {tagline}")
    desc = _profile_field_value(profile, "description")
    if desc:
        lines.append(f"- What they do: {desc[:300]}")
    props = []
    for item in (profile.get("value_propositions") or [])[:3]:
        v = _clean(item.get("value") if isinstance(item, dict) else item)
        if v:
            props.append(v)
    if props:
        lines.append("- Value propositions (verbatim): " + " | ".join(props))
    audience = _profile_field_value(profile, "audience_type")
    if audience:
        lines.append(f"- Audience: {audience}")
    langs = [str(x) for x in (profile.get("languages") or []) if x]
    if langs:
        lines.append("- Site languages: " + ", ".join(langs))
    return "\n".join(lines)


def build_llm_concept_prompt(
    brief: PosterBrief,
    caller: Optional[Any] = None,
    profile: dict[str, Any] | None = None,
) -> str:
    """LLM art-director: invent a UNIQUE, text-free visual concept per business.

    Falls back to the static build_creative_prompt() when no caller is supplied or
    the call fails. ZERO HALLUCINATION: the concept is purely VISUAL (a metaphor
    for what the business does) — it states no factual claims; the real copy stays
    in the overlay. The image is always text-free (text is overlaid later).

    When `profile` is given, the concept is grounded in the brand's scraped
    PERSONA (verbatim tagline / description / value props / audience / languages)
    and its VISUAL IDENTITY: the brand palette must drive the scene's color story,
    so the poster reads as THIS brand, not a generic category visual.
    """
    if caller is None:
        return build_creative_prompt(brief)

    offerings = "; ".join([o for o in (brief.offerings or [])[:5] if o]) or (brief.category or "its offerings")
    palette = ", ".join(brief.palette_hex[:4]) or "a premium brand palette"
    persona = _persona_lines(profile)
    system = (
        "You are an award-winning advertising art director. Invent ONE striking, "
        "surreal or metaphorical VISUAL concept for a premium vertical ad poster for "
        "the given business, written as a detailed image-generation prompt.\n"
        "STRICT RULES:\n"
        "- ONE bold hero concept — a visual metaphor for what the business does; not a busy scene.\n"
        "- EMBODY the brand persona below: the concept's subject, mood, and cultural "
        "context must feel like THIS specific brand, not its generic category.\n"
        "- The brand palette is the scene's DOMINANT color story (lighting, surfaces, "
        "atmosphere) — accent tones may vary, but the brand colors must lead.\n"
        "- Respect the audience's cultural context (e.g. Arabic-language brands: "
        "regionally authentic settings, props, and people — never clichés).\n"
        "- Photorealistic, editorial, high-end campaign aesthetic; cinematic lighting.\n"
        "- Leave GENEROUS empty negative space (lower third + margins) for text added later.\n"
        "- ABSOLUTELY NO text, words, letters, numbers, logos, or signage in the image.\n"
        "- Vertical 4:5. Purely visual: no factual claims, prices, or guarantees."
    )
    user = (
        f"Business: {brief.business_name}\n"
        f"Category: {brief.category}\n"
        f"Real offerings: {offerings}\n"
        f"Tone: {brief.tone or 'premium'}\n"
        f"Brand palette: {palette}\n"
        + (f"\nBrand persona (all verbatim from the real website):\n{persona}\n" if persona else "")
        + "\nReturn concept_title and a vivid, text-free image_prompt."
    )

    try:
        concept, _usage = caller(system, user, _CreativeConceptResponse, group_name="poster_concept")
        prompt = (getattr(concept, "image_prompt", "") or "").strip()
    except Exception:
        return build_creative_prompt(brief)

    if not prompt:
        return build_creative_prompt(brief)

    # Reinforce the hard constraints regardless of what the LLM returned.
    return (
        f"{prompt}\n\nBrand color palette: {palette}.\n"
        "ABSOLUTELY NO text, words, letters, numbers, logos, or signage anywhere; "
        "reserve clean empty space (lower third + a top corner) for a logo and a few "
        "words overlaid later. Vertical 4:5 poster, advertising-campaign style."
    )