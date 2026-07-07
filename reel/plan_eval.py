"""Evaluate a reel PLAN before the expensive Veo render (owner: 'evaluate the reel before it comes
out'). Deterministic — no LLM, no network — so it's a cheap pre-flight gate that catches a weak plan
(doesn't name the brand, no CTA, mostly text-free, all-same-scene, unreadable pacing) BEFORE we spend
10-15 minutes rendering it. The compositor's scene_qa still checks each RENDERED clip afterwards; this
checks the STRUCTURE up front so a bad plan is regenerated cheaply, not rendered.

Applies the STRANGER TEST + the caption-craft rules we adopted (name the brand + the offering, a real
CTA, caption-driven, scene variety, readable durations). Never raises."""
from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel


class ReelPlanVerdict(BaseModel):
    ok: bool = True
    score: int = 0            # 0..100, higher is better
    issues: list[str] = []    # human-readable failures, worst first


_WORD = re.compile(r"[A-Za-z؀-ۿ0-9]{2,}")


def _tokens(s: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(s or "")}


def _fv(profile: Any, key: str) -> str:
    if not isinstance(profile, dict):
        return ""
    v = profile.get(key)
    if isinstance(v, dict):
        v = v.get("value")
    return str(v or "")


def _offering_tokens(profile: Any) -> set[str]:
    out: set[str] = set()
    for o in (profile.get("offerings") or []) if isinstance(profile, dict) else []:
        name = o.get("name") if isinstance(o, dict) else o
        out |= _tokens(str(name or ""))
    return {t for t in out if len(t) >= 3}


def evaluate_reel_plan(reel: Any, *, profile: Optional[dict] = None,
                       featured: bool = False) -> ReelPlanVerdict:
    """Score a CreativeReel plan against the stranger test + caption-craft rules. `reel` is a
    CreativeReel (has .scenes with .on_screen_text/.voiceover/.duration_s/.image_index, + .cta)."""
    scenes = list(getattr(reel, "scenes", None) or [])
    if not scenes:
        return ReelPlanVerdict(ok=False, score=0, issues=["no scenes in the plan"])

    caps = [(getattr(s, "on_screen_text", "") or "").strip() for s in scenes]
    vos = [(getattr(s, "voiceover", "") or "").strip() for s in scenes]
    all_text = " ".join(caps + vos + [getattr(reel, "cta", "") or "", getattr(reel, "hook", "") or ""])
    all_tok = _tokens(all_text)

    issues: list[str] = []
    score = 100

    # 1) STRANGER TEST — names the brand somewhere in the spoken/on-screen copy.
    brand_tok = {t for t in _tokens(_fv(profile, "name")) if len(t) >= 3}
    if brand_tok and not (brand_tok & all_tok):
        issues.append("never names the brand (stranger test)")
        score -= 30

    # 2) STRANGER TEST — says what it offers: an offering/service name (or the category) appears.
    off_tok = _offering_tokens(profile)
    cat_tok = _tokens(_fv(profile, "category"))
    if (off_tok or cat_tok) and not ((off_tok & all_tok) or (cat_tok & all_tok)):
        issues.append("never names a specific offering/service or the category")
        score -= 20

    # 3) A real CTA on the last scene (a caption or a spoken line, or reel.cta set).
    last_has_cta = bool(caps[-1] or vos[-1] or (getattr(reel, "cta", "") or "").strip())
    if not last_has_cta:
        issues.append("no CTA on the final scene")
        score -= 15

    # 4) CAPTION-DRIVEN — at least half the scenes carry a caption (most people watch muted).
    n_caps = sum(1 for c in caps if c)
    if n_caps < max(1, (len(scenes) + 1) // 2):
        issues.append(f"mostly text-free ({n_caps}/{len(scenes)} scenes captioned)")
        score -= 15

    # 5) Readable captions — no caption longer than 6 words (a sentence flashes by).
    long_caps = [c for c in caps if len(c.split()) > 6]
    if long_caps:
        issues.append(f"{len(long_caps)} caption(s) too long to read (>6 words)")
        score -= 10

    # 6) SCENE VARIETY (non-featured) — not every scene rides the SAME photo.
    if not featured and len(scenes) > 2:
        idxs = [getattr(s, "image_index", 0) for s in scenes]
        if len(set(idxs)) == 1:
            issues.append("every scene uses the same photo (no scene variety)")
            score -= 10

    score = max(0, score)
    return ReelPlanVerdict(ok=not issues, score=score, issues=issues)
