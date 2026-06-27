"""Evidence Ledger — Step 2 BEFORE/AFTER measurement (the blocking gate).

Step 1 measured the problem (read-only). Step 2 turns the gate ON in
`build_creative_concept(..., enforce_grounding=True)`. This harness measures the delta:
the SAME live LLM concept generation, gate OFF (before) vs ON (after), N passes per
brand, counting customer-facing copy fields that carry an UNSOURCED falsifiable claim.

Generation is stochastic, so we average over N passes and report rates, not a single
run. Needs a live caller (Gemini/Vertex).

Run:  python -m grounding.measure_step2 [--passes N]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

from grounding.ledger import EvidenceLedger
from grounding.measure_step1 import CORPUS, _load, _unwrap


def _concept_fields(profile: dict, caller: Any, *, enforce: bool) -> dict[str, str]:
    from poster.concept import build_creative_concept
    c = build_creative_concept(profile, caller=caller, enforce_grounding=enforce)
    fields = {"headline": c.headline or "", "subheadline": c.subheadline or "", "cta": c.cta or ""}
    for i, chip in enumerate(c.proof_points or []):
        fields[f"chip_{i}"] = str(chip)
    return fields


def main(argv: list[str]) -> int:
    passes = 2
    for i, a in enumerate(argv):
        if a == "--passes" and i + 1 < len(argv):
            passes = max(1, int(argv[i + 1]))

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    try:
        from business_profile.llm import default_caller
        caller = default_caller(strong=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[caller] {exc}")
        caller = None
    if caller is None:
        print("[caller] no LLM caller -> cannot measure (needs Gemini/Vertex).")
        return 1

    agg = {"before": {"fields": 0, "unsourced": 0, "bad_fields": 0},
           "after": {"fields": 0, "unsourced": 0, "bad_fields": 0}}

    for path in CORPUS:
        raw = _load(path)
        if raw is None:
            continue
        profile = _unwrap(raw)
        nm = profile.get("name")
        name = nm.get("value") if isinstance(nm, dict) else (nm or path)
        ledger = EvidenceLedger.from_profile(profile)
        per = {"before": [0, 0], "after": [0, 0]}  # [unsourced_claims, bad_fields] summed
        nfields = {"before": 0, "after": 0}
        for mode, enforce in (("before", False), ("after", True)):
            for _ in range(passes):
                try:
                    rep = ledger.audit_fields(_concept_fields(profile, caller, enforce=enforce))
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! {name} [{mode}] failed: {type(exc).__name__}: {exc}")
                    continue
                per[mode][0] += rep.total_unsourced
                per[mode][1] += len(rep.unsourced_fields)
                nfields[mode] += len(rep.field_audits)
                agg[mode]["fields"] += len(rep.field_audits)
                agg[mode]["unsourced"] += rep.total_unsourced
                agg[mode]["bad_fields"] += len(rep.unsourced_fields)
        print(f"\n=== {name} ({passes} passes) ===")
        print(f"   BEFORE (gate off): unsourced_claims={per['before'][0]}  "
              f"bad_fields={per['before'][1]}/{nfields['before']}")
        print(f"   AFTER  (gate on) : unsourced_claims={per['after'][0]}  "
              f"bad_fields={per['after'][1]}/{nfields['after']}")

    print("\n" + "=" * 60)
    print(f"STEP 2 BEFORE/AFTER — blocking gate ({passes} passes/brand, {len(CORPUS)} brands)")
    print("=" * 60)
    for mode in ("before", "after"):
        a = agg[mode]
        pct = (100.0 * a["bad_fields"] / a["fields"]) if a["fields"] else 0.0
        label = "BEFORE (gate OFF)" if mode == "before" else "AFTER  (gate ON) "
        print(f"{label}: copy_fields={a['fields']}  UNSOURCED_claims={a['unsourced']}  "
              f"fields_with_a_fabricated_claim={a['bad_fields']} ({pct:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
