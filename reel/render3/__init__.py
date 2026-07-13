"""Render #3 — the story-first, consistency-locked reel pipeline (owner prompt pack,
reel_consistency_prompt_pack.md, adopted verbatim per its §10 directive).

Kills the three confirmed roots from render #2 — protagonist drift, no visual thread,
junk screens — BY MECHANISM, not by hope-in-prompt:

    D1-D3 Director (1 LLM call, strict JSON)
      -> G1 lint (schema + hard rules + the Ledger VO<->EVIDENCE trace)
      -> Character sheet (1 Nano Banana call -> one 3-view reference image)
      -> HITL #1  [HARD STOP: owner approves CONCEPT + PROTAGONIST CARD;
                   zero further spend before approval]
      -> Seeds (Nano Banana, reference sheet ATTACHED to every call;
                locked blocks byte-for-byte, sha256-checked)
      -> G2 gate [BLOCKING: vision verdict on the contact sheet; targeted
                  regen <=3; else RuntimeError — Veo never fires]
      -> Veo 3.1 image-to-video per shot (VERIFIED seeds only)
      -> Assemble + VO (Arabic TTS, in post) -> HITL #2 -> publish
"""
from .director import (
    G1Report, ReelTreatment, direct_reel, evidence_bullets_from_profile, g1_lint,
)

__all__ = ["ReelTreatment", "G1Report", "direct_reel", "g1_lint",
           "evidence_bullets_from_profile"]
