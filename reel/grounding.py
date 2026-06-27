"""Reel copy grounding — read-only audit primitive (Evidence-Ledger Step 1 for the reel).

The reel is the LAST customer-facing creative surface still OUTSIDE the Evidence-Ledger
brand-safety trail (see `grounding/audit.py` UNGATED_SURFACES). This module is the FIRST,
read-only step toward closing that gap: it APPLIES the existing `grounding.EvidenceLedger`
to the reel's copy surfaces so we can MEASURE how often a reel line carries a HARD CLAIM with
no source in the brand's evidence. It BLOCKS NOTHING — no softening, no regenerate (that is a
later step); it only audits.

Two copy surfaces (verified from the reel code):
  * The CREATIVE path (`reel.creative_director.design_creative_reel`, `--creative`) — an Opus
    call that GENERATES, per scene, a persuasive `voiceover` (spoken via TTS) and an
    `on_screen_text` caption (displayed), plus reel-level `hook`/`cta`. The real risk surface:
    an LLM with only a SOFT "invent no facts" instruction and nothing enforcing it — exactly
    the pre-Ledger poster situation. `concept`/`music_mood`/`veo_prompt` are internal
    production fields (never shown or spoken) -> excluded.
  * The DEFAULT path — `reel.voiceover.narration_lines(storyboard)`: one line per scene = the
    verbatim on-screen text already selected by `build_poster_brief`. Grounded BY CONSTRUCTION;
    audited only as the sanity FLOOR (the gate must not false-positive on grounded copy).

Pure/deterministic, never raises for ordinary input (reuses the Ledger's guarantees).
"""
from __future__ import annotations

from typing import Any

from grounding import AuditReport, EvidenceLedger


def creative_reel_copy_fields(creative_reel: Any) -> dict[str, str]:
    """The CUSTOMER-FACING copy of an Opus `CreativeReel`: the reel-level hook/cta plus each
    scene's spoken `voiceover` and displayed `on_screen_text` caption. Internal production
    fields (concept, music_mood, per-scene veo_prompt) are NOT customer-facing -> excluded."""
    fields: dict[str, str] = {}
    hook = (getattr(creative_reel, "hook", "") or "").strip()
    cta = (getattr(creative_reel, "cta", "") or "").strip()
    if hook:
        fields["hook"] = hook
    if cta:
        fields["cta"] = cta
    for i, sc in enumerate(getattr(creative_reel, "scenes", []) or []):
        vo = (getattr(sc, "voiceover", "") or "").strip()
        cap = (getattr(sc, "on_screen_text", "") or "").strip()
        if vo:
            fields[f"voiceover_{i}"] = vo
        if cap:
            fields[f"caption_{i}"] = cap
    return fields


def narration_copy_fields(storyboard: Any) -> dict[str, str]:
    """The DEFAULT path's spoken narration — one verbatim line per scene (the deterministic
    floor). Reuses `reel.voiceover.narration_lines` so it audits exactly what is spoken."""
    from reel.voiceover import narration_lines
    fields: dict[str, str] = {}
    for i, line in enumerate(narration_lines(storyboard)):
        line = (line or "").strip()
        if line:
            fields[f"scene_{i}"] = line
    return fields


def audit_reel_copy(profile: dict, fields: dict[str, str]) -> AuditReport:
    """Audit reel copy fields against the brand's real evidence — READ-ONLY. Returns an
    `AuditReport` whose `.export()` is the (claim -> source) trail and whose `.passes` /
    `.total_unsourced` size the problem. Never raises; an empty profile yields an empty
    ledger (a line with a hard claim then shows unsourced, a pure-paraphrase line passes)."""
    ledger = EvidenceLedger.from_profile(profile or {})
    return ledger.audit_fields(fields or {})
