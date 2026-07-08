"""Shared prompt contracts for the poster concept/copy/fidelity chain (Batch 2).

Two rules that several poster prompts each re-litigated (differently) are stated ONCE here,
the same way Batch 1 gave extraction one GROUNDING_CONTRACT:

- CRAFT_CONTRACT — the copy craft BAR. Replaces the scattered "senior / world-class /
  premium / award-winning" priming that made every brand's copy converge on the same
  imagined award-show ad. It sets a bar ("would this brand actually ship it") instead of a
  brag, bans the empty primers, and states the system's core philosophy: facts are gated,
  form is free.
- VERBATIM_RENDER_CONTRACT — the frozen-strings rule shared by the one-shot renderer and the
  OCR read-back reader, so the model that RENDERS the copy and the model that READS it back
  speak one language: render/read the approved lines character-for-character, Arabic as printed.
"""
from __future__ import annotations

CRAFT_CONTRACT = (
    "[CRAFT BAR]\n"
    "You are writing for a brand that will run this publicly. The bar is \"would this brand "
    "actually ship it,\" not \"does it sound like an ad.\" Earn attention through the ONE real "
    "specific thing this brand offers — not through adjectives. Banned as empty primers: "
    "premium, world-class, award-winning, cutting-edge, unparalleled, elevate, unleash. "
    "Specificity replaces intensity. The FACTS may only come from the evidence; the FORM is yours."
)

VERBATIM_RENDER_CONTRACT = (
    "[VERBATIM TEXT — render & read]\n"
    "The approved copy lines are FROZEN strings. Render/read them character-for-character: "
    "nothing added, removed, translated, reordered, or \"corrected.\" Arabic is copied as "
    "printed — dialectal spelling, dot counts (ت = 2, ث = 3), ة vs ه exactly. A single altered "
    "glyph is a fidelity failure, not a stylistic choice."
)

# The text-free/artefact-free rule for ALL background generation, stated once (Batch 3). Image
# models weight positives and prohibition-stacks underperform, so this is the ONE negative — the
# five scene prompts stop each re-stating "no text / no logo / no typography". Used both as a
# prose tail in the positive prompt and as the Imagen negative_prompt parameter (see IMAGE_NEGATIVE_TERMS).
IMAGE_NEGATIVE_CONTRACT = (
    "[IMAGE — TEXT-FREE & CLEAN]\n"
    "Generate a BACKGROUND scene only. No text, letters, numbers, words, typography, logos, "
    "watermarks, readable signage, price tags, menus, certificates, or UI with legible words — "
    "the text and logo are composited later. Avoid: distorted hands/faces, extra fingers, low "
    "quality, blur, clutter, busy overlay zones. Leave calm negative space for later overlay."
)

# The comma-separated terms for the Imagen `negative_prompt` PARAMETER (promoted verbatim from the
# old per-call `negative_prompt` in art_director so every image path shares ONE negative).
IMAGE_NEGATIVE_TERMS = (
    "text, words, letters, typography, logo, watermark, readable signage, "
    "price tags, UI screens with readable words, fake certificates with text, "
    "distorted hands, distorted faces, low quality, blurry, cluttered layout, "
    "busy overlay zones, overexposed, cartoonish"
)


# COMPLIANCE — ad-safety rules by category, ONE source of truth (Batch 3). Relocated out of the
# five aesthetic art-direction prompts so the SAME rules also cover the LLM image path and the reel
# (which had NO compliance gate), and so they feed the Meta Policy Linter. "no before/after" is
# policy, not art direction — it must live where every generation path can inject it.
_COMPLIANCE_MEDICAL = ("no identifiable patients, no before/after imagery, no procedures / needles "
                       "/ blood / invasive treatment or dramatic symptoms, no implied guaranteed results")
_COMPLIANCE_SKINCARE = ("no medical-treatment implication, no before/after comparisons, "
                        "no clinical claims, no skin-disease depiction")
_COMPLIANCE_FINLEGAL = "no guaranteed returns, outcomes, or results"

_COMPLIANCE_BY_CATEGORY = {
    "clinic": _COMPLIANCE_MEDICAL, "hospital": _COMPLIANCE_MEDICAL, "medical": _COMPLIANCE_MEDICAL,
    "beauty": _COMPLIANCE_SKINCARE, "skincare": _COMPLIANCE_SKINCARE, "cosmetics": _COMPLIANCE_SKINCARE,
    "professional_services": _COMPLIANCE_FINLEGAL, "services_b2b": _COMPLIANCE_FINLEGAL,
    "finance": _COMPLIANCE_FINLEGAL, "legal": _COMPLIANCE_FINLEGAL,
}


def compliance_for(category) -> str:
    """The ad-safety COMPLIANCE line for a category, ready to inject into any image / copy / motion
    prompt. Empty string when nothing beyond brand-safety applies (the `default`). One source, so
    the image path, the LLM path, the reel, and the policy linter all agree. Accepts a raw string,
    an enum (`.value`), or None."""
    cat = str(getattr(category, "value", category) or "").strip().lower()
    rules = _COMPLIANCE_BY_CATEGORY.get(cat)
    return f"COMPLIANCE (ad-safety, non-negotiable): {rules}." if rules else ""
