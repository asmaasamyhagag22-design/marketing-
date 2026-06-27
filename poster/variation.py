"""Per-run creative VARIATION for the poster.

Owner complaint: "every poster looks the same — same text design every run." The
design-spec LLM + the deterministic fallback both keyed only on the brand, so one
brand always produced one look. This injects a fresh, per-RUN creative direction
(mood / lighting / composition / energy) into the design-spec call, the Imagen
concept prompt, and the deterministic fallback — so the SAME brand renders a
DIFFERENT, still-on-brand poster each run.

Two truth domains: variation is PURE DESIGN (how it looks), never facts. It changes
mood/lighting/composition/layout — it does NOT touch the headline, offerings, CTA, or
any evidence-grounded copy. Idea adopted from TrendPulse's `build_variation_context`.

Reproducible: pass a `seed` (e.g. the CLI `--variation N`) for a deterministic look;
omit it for a fresh look every render.
"""
from __future__ import annotations

import random
import time
from typing import Optional

# Pure-design vocabularies — visual treatment only, no factual content.
_MOODS = [
    "bold and high-energy", "calm and editorial", "warm and inviting",
    "sleek premium-minimal", "vibrant and playful", "dramatic and cinematic",
    "fresh and airy", "confident and authoritative",
]
_LIGHTING = [
    "soft natural daylight", "warm golden-hour glow", "bright high-key light",
    "moody low-key with rich shadows", "crisp clean studio light",
    "soft diffused window light", "vivid saturated daylight",
]
_COMPOSITIONS = [
    "generous negative space around a single hero subject",
    "a bold tight close-up of the subject",
    "a wide environmental scene with depth",
    "layered depth with foreground interest",
    "a clean symmetrical, balanced frame",
    "dynamic diagonal energy and motion",
    "an elevated overhead flat-lay angle",
]
_ENERGY = [
    "minimal and restrained", "punchy and graphic",
    "elegant and refined", "lively and dynamic",
]


def build_variation(seed: Optional[int] = None) -> dict:
    """Pick one creative direction. `seed` -> deterministic (reproducible per index);
    None -> a fresh microsecond-seeded pick each call."""
    rng = random.Random(seed if seed is not None else int(time.time() * 1_000_000))
    return {
        "mood": rng.choice(_MOODS),
        "lighting": rng.choice(_LIGHTING),
        "composition": rng.choice(_COMPOSITIONS),
        "energy": rng.choice(_ENERGY),
        "seed": seed,
    }


def variation_seed_int(variation: Optional[dict]) -> Optional[int]:
    """A stable integer seed derived from a variation's design choices — used to vary
    the deterministic (no-LLM) design-spec fallback per run. None when no variation."""
    if not variation:
        return None
    if variation.get("seed") is not None:
        return int(variation["seed"])
    basis = "|".join(str(variation.get(k, "")) for k in ("mood", "lighting", "composition", "energy"))
    return abs(hash(basis)) % 1_000_000


def design_variation_cue(variation: Optional[dict]) -> str:
    """One line for the design-spec LLM — steer the COMPOSITION choices for this run."""
    if not variation:
        return ""
    return (
        "Creative direction for THIS render (make the composition feel "
        f"{variation['energy']} and {variation['mood']}; choose a layout, headline "
        "treatment and scrim that express it — stay on-brand, never change the words)."
    )


def concept_variation_cue(variation: Optional[dict]) -> str:
    """One phrase for the Imagen concept prompt — steer the SCENE's look for this run."""
    if not variation:
        return ""
    return (
        f"Overall feel: {variation['mood']}, {variation['energy']}. "
        f"Lighting: {variation['lighting']}. Composition: {variation['composition']}."
    )
