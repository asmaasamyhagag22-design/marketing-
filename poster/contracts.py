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
