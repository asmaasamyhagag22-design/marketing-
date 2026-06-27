"""Reel grounding — Step 1 measurement (READ-ONLY, no blocking).

Sizes the reel's grounding risk the same way `grounding/measure_step1.py` sized the poster's,
over the SAME saved-profile corpus. Nothing is blocked: we call the existing reel copy builders
and AUDIT their output against the Evidence Ledger.

Two paths per brand:
  A. DEFAULT narration path (`build_storyboard` caller=None -> `narration_lines`) — verbatim,
     no LLM. Expected ~0 unsourced: the sanity FLOOR proving the gate doesn't false-positive on
     genuinely grounded reel copy. Runs offline, ZERO cost. This is the number Step 1 produces.
  B. CREATIVE path (`reel.creative_director.design_creative_reel`, `--creative`) — the Opus
     GENERATION surface, the real risk. It costs money (one Opus call/brand), so it is OPT-IN:
     it runs only with `--creative` AND an `ANTHROPIC_API_KEY` present — never spends silently.

Run:  python -m grounding.measure_reel              (path A only, offline, default)
      python -m grounding.measure_reel --creative   (also path B; needs ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import os
import sys

# Windows cp1252 console crashes when printing Arabic — force UTF-8 (same as measure_step1).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

from grounding.ledger import AuditReport, EvidenceLedger
from grounding.measure_step1 import CORPUS, _load, _unwrap
from reel.grounding import audit_reel_copy, creative_reel_copy_fields, narration_copy_fields


def _narration_fields(profile: dict) -> dict[str, str]:
    """Path A — the default reel's verbatim spoken narration (no LLM; caller=None keeps the
    storyboard's art-director on its deterministic, offline fallback)."""
    from reel.from_profile import build_reel_brief
    from reel.storyboard import build_storyboard
    brief = build_reel_brief(profile)
    storyboard = build_storyboard(brief, profile=profile, caller=None)
    return narration_copy_fields(storyboard)


def _creative_fields(profile: dict) -> dict[str, str]:
    """Path B — the Opus-generated creative reel copy (the risk surface). Empty when Opus
    produced nothing (no key / no real photos / parse failure)."""
    from reel.creative_director import design_creative_reel
    photos = (profile.get("visual") or {}).get("content_images") or []
    reel = design_creative_reel(profile, photos, n_scenes=5)
    return creative_reel_copy_fields(reel) if reel else {}


def _print_report(tag: str, rep: AuditReport) -> None:
    flag = "OK " if rep.passes else "!! "
    print(f"  {flag}[{tag}] fields={len(rep.field_audits)} "
          f"with_claims={rep.fields_with_claims} unsourced={rep.total_unsourced}/{rep.total_claims}")
    for fa in rep.unsourced_fields:
        toks = ", ".join(f"{v.claim.kind}:{v.claim.token}" for v in fa.unsourced)
        print(f"       UNSOURCED {fa.field!r}: {fa.text!r}  ->  [{toks}]")


def main(argv: list[str]) -> int:
    do_creative = "--creative" in argv
    if do_creative:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("[creative] --creative requested but ANTHROPIC_API_KEY is not set -> path B "
                  "skipped (no spend). Running the offline floor only.\n")
            do_creative = False

    agg = {
        "A": {"fields": 0, "with_claims": 0, "claims": 0, "unsourced": 0, "bad_fields": 0, "n": 0},
        "B": {"fields": 0, "with_claims": 0, "claims": 0, "unsourced": 0, "bad_fields": 0, "n": 0},
    }

    def _accumulate(bucket: dict, rep: AuditReport) -> None:
        bucket["n"] += 1
        bucket["fields"] += len(rep.field_audits)
        bucket["with_claims"] += rep.fields_with_claims
        bucket["claims"] += rep.total_claims
        bucket["unsourced"] += rep.total_unsourced
        bucket["bad_fields"] += len(rep.unsourced_fields)

    for path in CORPUS:
        raw = _load(path)
        if raw is None:
            print(f"\n=== {path}: MISSING ===")
            continue
        profile = _unwrap(raw)
        nm = profile.get("name")
        name = nm.get("value") if isinstance(nm, dict) else (nm or path)
        ledger = EvidenceLedger.from_profile(profile)
        print(f"\n=== {name}  ({path})  evidence_entries={len(ledger.entries)} ===")

        # Path A — default verbatim narration (offline).
        try:
            repA = audit_reel_copy(profile, _narration_fields(profile))
            _print_report("A narration", repA)
            _accumulate(agg["A"], repA)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! path A failed: {type(exc).__name__}: {exc}")

        # Path B — Opus creative copy (opt-in, paid).
        if do_creative:
            try:
                fields = _creative_fields(profile)
                if not fields:
                    print("  .. path B: Opus produced no reel (no key/photos/parse) -> skipped")
                else:
                    repB = audit_reel_copy(profile, fields)
                    _print_report("B  creative", repB)
                    _accumulate(agg["B"], repB)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! path B (Opus) failed: {type(exc).__name__}: {exc}")

    # ---- THE NUMBER ----
    print("\n" + "=" * 64)
    print("REEL STEP 1 RESULT — unsourced hard-claim rate (read-only, nothing blocked)")
    print("=" * 64)
    for tag, label in (("A", "DEFAULT narration path (sanity floor)"),
                       ("B", "CREATIVE Opus path (the risk surface)")):
        a = agg[tag]
        if a["n"] == 0:
            print(f"{label}: not measured")
            continue
        pct = (100.0 * a["bad_fields"] / a["fields"]) if a["fields"] else 0.0
        print(f"{label}:")
        print(f"   brands={a['n']}  copy_fields={a['fields']}  fields_with_a_hard_claim={a['with_claims']}")
        print(f"   hard_claims={a['claims']}  UNSOURCED_claims={a['unsourced']}  "
              f"fields_that_would_be_REJECTED={a['bad_fields']} ({pct:.0f}% of copy fields)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
