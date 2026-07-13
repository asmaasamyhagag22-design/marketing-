"""§0 — the Render #3 pipeline orchestrator. Every gate spends before Veo does.

Two entrypoints around the HARD STOP:

  prepare_render3()   Director -> G1 -> character sheet -> HITL #1 package.
                      ZERO seed/Veo spend. The owner approves CONCEPT + PROTAGONIST
                      CARD before anything else runs (HITL law).
  continue_render3()  (after owner approval) seeds w/ refs -> G2 BLOCKING -> Veo
                      per shot from VERIFIED seeds -> assemble -> VO in post ->
                      HITL #2 (present; publish is the owner's).

Code-level invariant (§0, verbatim intent): no Veo request is constructed unless the
G2 verdict for the FULL current seed set is PASS — enforced by run_g2_loop raising
RuntimeError AND re-checked here explicitly.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .director import ReelTreatment, direct_reel, g1_lint
from .g2 import run_g2_loop
from .nano import generate_with_refs
from .prompts import character_sheet_prompt, locked_hashes, seed_prompt, veo_prompt

logger = logging.getLogger(__name__)


def prepare_render3(profile: dict, *, caller: Any, out_dir: "str | Path",
                    n_shots: int = 6, log=print) -> dict:
    """Stage 1 (pre-approval): Director -> G1 -> character sheet. Returns the HITL #1
    package {treatment, treatment_path, sheet_path, hashes} or {'error': ...}. On a G1
    failure the director gets ONE corrective retry (issues appended), then fail loud."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    t = direct_reel(profile, caller=caller, n_shots=n_shots)
    if t is None:
        return {"error": "director produced no valid treatment (after retry)"}
    rep = g1_lint(t, profile=profile, n_shots=n_shots)
    if not rep.ok:
        log(f"[g1] FAIL: {rep.issues} -> one corrective retry")
        t2 = direct_reel(
            profile, caller=caller, n_shots=n_shots,
            client_one_liner=f"(Fix these violations from your previous attempt: "
                             f"{'; '.join(rep.issues[:6])})")
        rep2 = g1_lint(t2, profile=profile, n_shots=n_shots) if t2 else None
        if not (t2 and rep2 and rep2.ok):
            return {"error": f"G1 lint failed twice: {(rep2.issues if rep2 else rep.issues)}"}
        t = t2
    hashes = locked_hashes(t)
    tp = out / "treatment.json"
    tp.write_text(t.model_dump_json(indent=2), encoding="utf-8")
    (out / "locked_hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")

    sheet_path = out / "character_sheet.png"
    generate_with_refs(character_sheet_prompt(t.character_sheet), sheet_path, refs=None,
                       log=log)
    log(f"[render3] HITL #1 ready — approve the CONCEPT + PROTAGONIST CARD before any "
        f"further spend: {tp} + {sheet_path}")
    return {"treatment": t, "treatment_path": str(tp), "sheet_path": str(sheet_path),
            "hashes": hashes}


def continue_render3(prep: dict, *, caller: Any, out_dir: "str | Path",
                     location_photos: Optional[dict[str, str]] = None,
                     screenshots: Optional[dict[int, str]] = None,
                     veo_provider: Any = None, max_g2_retries: int = 3,
                     log=print) -> dict:
    """Stage 2 (POST-approval only — HITL #1 is the owner's). Seeds -> G2 (blocking) ->
    Veo from verified seeds -> per-shot clips. Returns {clips, seeds, g2} — assembly/VO
    ride the existing reel toolchain downstream."""
    t: ReelTreatment = prep["treatment"] if isinstance(prep.get("treatment"), ReelTreatment) \
        else ReelTreatment.model_validate_json(
            Path(prep["treatment_path"]).read_text(encoding="utf-8"))
    hashes = prep["hashes"]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ref_sheet = Path(prep["sheet_path"]).read_bytes()

    def _refs_for(shot) -> tuple[list, bool, Optional[int]]:
        refs = [(ref_sheet, "image/png")]
        loc_attached = False
        shot_idx: Optional[int] = None
        loc = (location_photos or {}).get(shot.location)
        if loc and Path(loc).is_file():
            refs.append((Path(loc).read_bytes(), "image/jpeg"))
            loc_attached = True
        scr = (screenshots or {}).get(shot.id)
        if scr and Path(scr).is_file():
            refs.append((Path(scr).read_bytes(), "image/png"))
            shot_idx = len(refs)             # 1-based image index in the prompt
        return refs, loc_attached, shot_idx

    def _gen_seed(i: int) -> str:
        shot = t.shots[i]
        refs, loc_attached, scr_idx = _refs_for(shot)
        p = seed_prompt(t, shot, n_shots=len(t.shots),
                        location_photo_attached=loc_attached,
                        screenshot_index=scr_idx, hashes=hashes)
        # Pro lane for legible REAL_CONTENT screens without an attached screenshot (§6).
        pro = shot.screen_rule.startswith("REAL_CONTENT:") and scr_idx is None
        dst = out / f"seed_{shot.id:02d}.png"
        return str(generate_with_refs(p, dst, refs=refs, pro=pro, log=log))

    seeds = [_gen_seed(i) for i in range(len(t.shots))]
    verdict = run_g2_loop(seeds, ref_sheet, regen=_gen_seed, caller=caller,
                          max_retries=max_g2_retries, log=log)
    # §0 code-level invariant — belt AND braces (run_g2_loop already raises on failure).
    if verdict.verdict != "PASS":
        raise RuntimeError(f"G2 FAIL — Veo spend refused: {verdict.model_dump()}")

    if veo_provider is None:
        from reel.video_provider import VeoProvider
        veo_provider = VeoProvider()
    clips: list[str] = []
    for i, shot in enumerate(t.shots):
        clip = out / f"clip_{shot.id:02d}.mp4"
        veo_provider.generate(veo_prompt(t, shot), out_path=clip,
                              duration_s=float(shot.duration_s),
                              width=1080, height=1920,
                              reference_image=seeds[i])
        log(f"[render3] shot {shot.id}/{len(t.shots)} animated from VERIFIED seed")
        clips.append(str(clip))
    return {"clips": clips, "seeds": seeds, "g2": verdict.model_dump(),
            "treatment": t}
