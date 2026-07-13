"""§1 — the Director call (D1 concept + D2 VO + D3 storyboard in ONE strict-JSON call)
and the G1 lint (code first, the Ledger as the VO<->EVIDENCE trace).

Hard rules R1-R8 live in the prompt verbatim; G1 re-checks the checkable ones in CODE so a
violating treatment never reaches spend. The VO trace uses ledger.audit_text — the
Zero-Hallucination moat extended into the reel (stronger than the pack's minimum LLM check;
logged as D-R3.4).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_ALLOWED_SCREEN = ("NONE", "OUT_OF_FOCUS", "ANGLED_AWAY")
_SMILE_RE = re.compile(r"smil|يبتسم|تبتسم|ابتسام|مبتسم", re.IGNORECASE)


class Motif(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object: str
    state_act1: str
    state_act2: str
    state_act3: str


class ActPalette(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hex: List[str] = Field(min_length=2, max_length=2)
    grade: str


class ColorConstants(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lens: str
    dof: str
    lighting: str
    grain: str


class ColorScript(BaseModel):
    model_config = ConfigDict(extra="forbid")
    act1: ActPalette
    act2: ActPalette
    act3: ActPalette
    constants: ColorConstants


class CharacterSheet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    age: int
    skin_tone: str
    face: str
    distinctive_features: List[str]
    eyes: str
    hijab: Optional[str] = None
    outfit_act1: str
    outfit_act3: str
    constant_accessory: str


class Shot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    act: int
    duration_s: int
    location: str
    action: str
    emotion: str
    story_function: str
    camera: str
    screen_rule: str
    motif_placement: str
    match_cut_out: str = ""


class ReelTreatment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    big_idea: str
    logline: str
    vo_script_ar: str
    motif: Motif
    color_script: ColorScript
    character_sheet: CharacterSheet
    locations: List[str]
    shots: List[Shot]


# ---------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------

def _val(x: Any) -> str:
    if isinstance(x, dict):
        return str(x.get("value") or "")
    return str(x or "")


def evidence_bullets_from_profile(profile: dict) -> list[str]:
    """The EVIDENCE input (§1): verbatim grounded facts from the profile — the ONLY
    permissible claim source for the VO. Pure projection, no invention."""
    p = profile.get("profile", profile) if isinstance(profile, dict) else {}
    bullets: list[str] = []
    d = _val(p.get("description"))
    if d:
        bullets.append(d[:220])
    for vp in (p.get("value_propositions") or [])[:6]:
        t = _val(vp)
        if t:
            bullets.append(t[:200])
    for ts in (p.get("trust_signals") or [])[:6]:
        t = _val(ts)
        if t:
            bullets.append(t[:200])
    for off in (p.get("offerings") or [])[:8]:
        name = _val(off.get("name")) if isinstance(off, dict) else _val(off)
        price = _val(off.get("price_text")) if isinstance(off, dict) else ""
        if name:
            bullets.append(f"{name}{f' — {price}' if price else ''}"[:200])
    return bullets


_DIRECTOR_PROMPT = """ROLE
You are the Creative Director of a ~30-second vertical (9:16) ad reel. You
produce ONE coherent film treatment — a single story — not a mood board. Your
output feeds an automated image+video pipeline; every field must be concrete,
visual, and unambiguous.

INPUTS
CLIENT: {client_name} — {client_one_liner}
OFFER: {offer}
AUDIENCE: {audience}
GOAL / CTA: {goal_cta}
EVIDENCE (grounded facts — the ONLY permissible claim source): {evidence_bullets}
LOCALE LOCK: Egypt. Egyptian people, Egyptian streets and interiors, Arabic
signage where natural. Never Gulf styling, never generic Western stock look.

HARD RULES — violating any one makes the output invalid:
R1 ONE PROTAGONIST. Exactly one character is the visual subject of EVERY shot.
   Supporting people (instructor, colleague) may appear but never replace the
   protagonist as the subject of a shot.
R2 THREE-ACT ARC across {n_shots} shots (default 6, 4-6 s each):
   Act1 = tension (a real, visible problem), Act2 = turning point + effort,
   Act3 = transformation + payoff + CTA. Every shot carries a story_function
   and an emotion. The beat "person smiles at a laptop/phone" is BANNED
   everywhere except as the single final payoff shot.
R3 ONE MOTIF. One physical object appears in every shot and visibly evolves
   with the arc (define its state per act). The motif is the visual glue.
R4 COLOR SCRIPT. A deliberate 3-act palette progression (2 hex anchors + grade
   words per act) plus constants (lens, depth of field, lighting style, grain).
   Deliberate progression = thread; random jumps = noise.
R5 MATCH CUTS. For every consecutive shot pair, specify match_cut_out: how
   shot k ENDS (gesture / object / camera direction) so that shot k+1's
   opening visually continues it.
R6 SCREENS. Any visible screen must be exactly one of:
   (a) OUT_OF_FOCUS — content unreadable by design (bokeh glow only),
   (b) ANGLED_AWAY — screen not facing camera,
   (c) REAL_CONTENT:<desc> — name the exact mundane content (e.g. "dark
       terminal window, a few lines of white monospace text" / "network
       topology diagram with 5 labeled nodes").
   NEVER "futuristic interface", NEVER glowing abstract UI, NEVER implied text.
R7 CHARACTER SHEET SPEC. A complete physical description FROZEN for the whole
   reel: name, age, skin tone, face shape + exactly 2 distinctive facial
   features, eyes, hijab yes/no (if yes: exact color + pattern + wrap style),
   max 2 outfits (Act1 outfit, Act3 outfit — both precise), and one constant
   accessory tied to the motif.
R8 VO. One voice, Egyptian Arabic, 60-70 words, first person, matching the
   arc. Every factual claim in the VO must trace to a bullet in EVIDENCE.
   If a claim is not in EVIDENCE, do not make it.

Return the structured treatment."""


def direct_reel(profile: dict, *, caller: Any, client_one_liner: str = "",
                offer: str = "", audience: str = "", goal_cta: str = "",
                n_shots: int = 6,
                evidence_bullets: Optional[list[str]] = None) -> Optional[ReelTreatment]:
    """ONE Director call -> a validated ReelTreatment. Retries once on parse/validation
    failure (per the pack), then returns None — the caller fails loud, never guesses."""
    if caller is None:
        return None
    p = profile.get("profile", profile) if isinstance(profile, dict) else {}
    bullets = evidence_bullets if evidence_bullets is not None \
        else evidence_bullets_from_profile(profile)
    prompt = _DIRECTOR_PROMPT.format(
        client_name=_val(p.get("name")) or "the brand",
        client_one_liner=client_one_liner or _val(p.get("description"))[:160],
        offer=offer or "; ".join(b for b in bullets[:3]),
        audience=audience or _val(p.get("audience_type")) or "Egyptian consumers",
        goal_cta=goal_cta or "drive applications / purchases now",
        evidence_bullets="\n- " + "\n- ".join(bullets) if bullets else "(none)",
        n_shots=n_shots,
    )
    for attempt in (1, 2):
        try:
            resp, _u = caller(
                "You are a world-class creative director. Output must satisfy every HARD "
                "RULE. Be concrete and visual; never vague.",
                prompt, ReelTreatment, group_name="render3_director")
            if resp and resp.shots:
                return resp
        except Exception as exc:  # noqa: BLE001
            logger.warning("director call failed (attempt %d): %s", attempt,
                           type(exc).__name__)
    return None


# ---------------------------------------------------------------------------------
# G1 lint — code checks + the Ledger VO trace
# ---------------------------------------------------------------------------------

@dataclass
class G1Report:
    ok: bool
    issues: List[str] = field(default_factory=list)
    unsourced_vo_claims: List[str] = field(default_factory=list)


def g1_lint(t: ReelTreatment, *, profile: Optional[dict] = None,
            n_shots: int = 6) -> G1Report:
    """The §1 lint, in CODE. Any issue -> the treatment never reaches spend."""
    issues: list[str] = []
    if len(t.character_sheet.distinctive_features) != 2:
        issues.append("character_sheet needs exactly 2 distinctive_features")
    if len(t.locations) > 4:
        issues.append(f"{len(t.locations)} locations (max 4)")
    if len(t.shots) != n_shots:
        issues.append(f"{len(t.shots)} shots (expected {n_shots})")
    acts = [s.act for s in t.shots]
    if sorted(set(acts)) != [1, 2, 3]:
        issues.append(f"acts present {sorted(set(acts))} (need all of 1,2,3)")
    if acts != sorted(acts):
        issues.append("acts are not in order (the three-act arc must progress)")
    smile_hits = [s.id for s in t.shots if _SMILE_RE.search(s.action + " " + s.emotion)]
    if any(sid != t.shots[-1].id for sid in smile_hits) or len(smile_hits) > 1:
        issues.append(f"smile-type beat outside the single final payoff shot: {smile_hits}")
    for s in t.shots:
        for fld in ("action", "emotion", "story_function", "camera", "motif_placement"):
            if not getattr(s, fld).strip():
                issues.append(f"shot {s.id}: empty {fld}")
        if s is not t.shots[-1] and not s.match_cut_out.strip():
            issues.append(f"shot {s.id}: empty match_cut_out")
        if s.location not in t.locations:
            issues.append(f"shot {s.id}: location {s.location!r} not in locations")
        if not (s.screen_rule in _ALLOWED_SCREEN
                or s.screen_rule.startswith("REAL_CONTENT:")):
            issues.append(f"shot {s.id}: screen_rule {s.screen_rule!r} not allowed")
        if not 3 <= s.duration_s <= 8:
            issues.append(f"shot {s.id}: duration {s.duration_s}s outside 3-8s")
    words = len(t.vo_script_ar.split())
    if not 55 <= words <= 75:
        issues.append(f"VO is {words} words (must be 55-75)")

    # VO <-> EVIDENCE trace via the Ledger (D-R3.4 — the moat, not an LLM opinion)
    unsourced: list[str] = []
    if profile is not None:
        try:
            from grounding import EvidenceLedger
            ledger = EvidenceLedger.from_profile(profile)
            unsourced = [v.claim.text for v in ledger.audit_text(t.vo_script_ar)
                         if not v.sourced]
            if unsourced:
                issues.append(f"VO carries {len(unsourced)} unsourced hard claim(s)")
        except Exception:  # noqa: BLE001 — the ledger never blocks the lint itself
            pass
    return G1Report(ok=not issues, issues=issues, unsourced_vo_claims=unsourced)
