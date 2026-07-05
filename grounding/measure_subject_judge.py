# -*- coding: utf-8 -*-
"""Evidence Ledger — C2-residual SUBJECT-JUDGE accuracy measurement (LIVE, needs a caller).

The ledger's deterministic gate can't decide, on a TOKEN-DISJOINT subject that shares a value,
whether it's an acceptable synonym/inflection ("5000 experts" vs "5000 youth") or a fabrication
("100 gifts" vs "100 stores"). `grounding.subject_judge.make_subject_judge` wraps one cheap Flash
call into that judgment. Its MECHANISM is hermetically tested (tests/test_ledger_subject_judge.py
with a mock), but this script measures its real ACCURACY on a labeled, balanced, bilingual
(EN + AR) set of realistic claim/evidence pairs — the moat's strict mode is only as good as this
judgment.

What matters most is the DANGEROUS direction: a fabrication waved through (expected reject, judge
accepts) is a moat FAILURE; an over-block (expected accept, judge rejects) is merely the copy
getting softened/regenerated — safe. The set therefore includes subtle adversarial fabrications
(near-miss numbers that both look like credentials).

Run:  python -m grounding.measure_subject_judge          # ~45 Flash calls
      python -m grounding.measure_subject_judge --check   # build the caller only, 0 calls

Measured 2026-07-05 (gemini-2.5-flash): 98% (44/45); fabrications caught 25/25 (0 missed);
real claims kept 19/20 (1 safe over-block on a borderline AR "largest pharmacy" vs "biggest
pharmacy chain"); 0 abstentions.
"""
from __future__ import annotations

import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# (token, claim, evidence, expected_same_subject, note)
CASES: list[tuple[str, str, str, bool, str]] = [
    # --- TRUE: one subject via synonym/inflection -> ACCEPT ---
    ("5000", "5000 experts trained every year", "we train 5000 youth annually", True, "experts=youth"),
    ("100", "100 certified coaches on our team", "our 100 accredited trainers", True, "coaches=trainers"),
    ("30", "30 branches nationwide", "we have 30 stores across Egypt", True, "branches=stores"),
    ("50", "50 doctors on staff", "50 physicians available", True, "doctors=physicians"),
    ("best", "the best pizza in Cairo", "we make the finest pies in town", True, "best pizza=finest pies"),
    ("largest", "the largest jewelry collection", "the biggest range of jewels", True, "largest=biggest"),
    ("24", "open 24/7 for you", "available around the clock, 24 hours", True, "24/7=24h"),
    ("1000", "over 1000 five-star reviews", "more than 1000 happy customer ratings", True, "reviews=ratings"),
    ("15", "15 years of trusted care", "serving families for 15 years", True, "same 15 years"),
    ("200", "200 menu items to choose from", "our menu has 200 dishes", True, "items=dishes"),
    ("الرواد", "روّاد التحول الرقمي", "نحن الرواد الرقميون", True, "AR inflection رواد"),
    ("5000", "دربنا 5000 خبير", "ندرب 5000 شاب سنويا", True, "AR experts=youth"),
    ("أكبر", "أكبر صيدلية في مصر", "أضخم سلسلة صيدليات", True, "AR largest pharmacy (borderline)"),
    ("40", "40 عيادة في أنحاء البلاد", "لدينا 40 فرعا طبيا", True, "AR clinics=branches"),
    ("500", "500 skilled artisans", "a workforce of 500 master craftsmen", True, "artisans=craftsmen"),
    ("20", "20 years of heritage", "20 years of dedicated craftsmanship", True, "same 20 years"),
    ("10000", "10000 satisfied patients", "10000 happy clients treated", True, "patients=clients"),
    ("أفضل", "أفضل خدمة عملاء", "خدمة عملاء لا مثيل لها", True, "AR best=unmatched"),
    ("أكبر", "أكبر تشكيلة مجوهرات", "أوسع مجموعة من المجوهرات", True, "AR largest=widest jewelry"),
    ("300", "300 corporate partners", "300 business clients on board", True, "partners=business clients"),

    # --- FALSE: shared value, UNRELATED subject -> REJECT (fabrication) ---
    ("100", "100 free gifts with purchase", "we have 100 stores nationwide", False, "gifts vs stores"),
    ("50", "50% off everything today", "50 years in business", False, "discount vs years"),
    ("best", "the best coffee in town", "best regards, the team", False, "coffee vs sign-off"),
    ("5000", "5000 products in stock", "our 5000 sq ft showroom", False, "products vs area"),
    ("3", "ranked #3 in the country", "3 easy steps to order", False, "rank vs steps"),
    ("10", "10 million active users", "10 minute delivery guaranteed", False, "users vs minutes"),
    ("40", "40% faster results", "a team of 40 employees", False, "speed vs headcount"),
    ("2", "2x more effective formula", "visit our 2 locations", False, "multiplier vs locations"),
    ("first", "the first name in beauty", "take the first door on your left", False, "rank vs direction"),
    ("500", "500 happy brides", "priced at 500 EGP", False, "count vs price"),
    ("50", "خصم 50% على كل المنتجات", "50 عاما من الخبرة", False, "AR discount vs years"),
    ("100", "100 هدية مجانية", "لدينا 100 فرع", False, "AR gifts vs branches"),
    ("أول", "الأول في مجال التجميل", "الطابق الأول على اليمين", False, "AR first(rank) vs first floor"),
    ("20", "20 مليون عميل", "التوصيل خلال 20 دقيقة", False, "AR customers vs minutes"),
    # subtle adversarial fabrications (both sides look like credentials)
    ("50", "50 years of experience", "winner of 50 industry awards", False, "years vs awards"),
    ("3", "awarded 3 Michelin stars", "3 convenient locations", False, "stars vs locations"),
    ("100", "100% organic ingredients", "100 signature recipes", False, "purity% vs recipe count"),
    ("1", "the #1 choice of dentists", "backed by a 1 year warranty", False, "rank vs warranty"),
    ("25", "25 years in practice", "enjoy a 25% discount", False, "years vs discount"),
    ("5", "5-star rated service", "5 branches to serve you", False, "rating vs branches"),
    ("12", "12 months interest-free", "a team of 12 specialists", False, "term vs headcount"),
    ("2000", "trusted since 2000", "over 2000 clients served", False, "founding year vs count"),
    ("10", "10 سنوات من الخبرة", "حاصلون على 10 جوائز", False, "AR years vs awards"),
    ("5", "خدمة بتقييم 5 نجوم", "لدينا 5 فروع", False, "AR rating vs branches"),
    ("18", "18 years of heritage", "open until 18:00 daily", False, "years vs closing hour"),
]


def main(argv: list[str]) -> int:
    # Entry point: load .env read-only (like api/main.py) so the Flash caller finds credentials.
    try:
        from pathlib import Path

        from dotenv import load_dotenv
        for _cand in (Path(__file__).resolve().parent.parent / ".env",):
            if _cand.exists():
                load_dotenv(_cand, override=False)
    except Exception:
        pass

    from business_profile.llm.caller import default_caller
    from grounding.subject_judge import make_subject_judge

    caller = default_caller(strong=False)
    n_true = sum(1 for c in CASES if c[3])
    print(f"caller: {'built' if caller else 'MISSING'} | cases: {len(CASES)} "
          f"(accept={n_true}, reject={len(CASES) - n_true})")
    if caller is None:
        print("No Gemini caller (set GEMINI_API_KEY / GOOGLE_CLOUD_PROJECT). Aborting.")
        return 1
    if "--check" in argv:
        print("--check: caller builds; no LLM calls made.")
        return 0

    judge = make_subject_judge(caller)
    caught = missed = kept = overblocked = abstained = correct = 0
    for token, claim, evidence, expected, note in CASES:
        got = judge(claim, evidence, token)
        effective = True if got is None else got   # None -> lenient accept
        if got is None:
            abstained += 1
        if effective == expected:
            correct += 1
        if expected is False:
            caught += int(effective is False)
            missed += int(effective is True)      # DANGEROUS: fabrication waved through
        else:
            kept += int(effective is True)
            overblocked += int(effective is False)  # safe: copy just gets softened
        print(f"  {'OK ' if effective == expected else 'XX '} "
              f"exp={str(expected):<5} got={str(got):<5} [{note}]")

    fab = len(CASES) - n_true
    print("\n==== SUBJECT-JUDGE ACCURACY ====")
    print(f"overall: {correct}/{len(CASES)} = {correct / len(CASES):.0%}")
    print(f"fabrications CAUGHT: {caught}/{fab}  MISSED (moat failure): {missed}/{fab}")
    print(f"real claims KEPT: {kept}/{n_true}  over-blocked (safe): {overblocked}/{n_true}")
    print(f"abstained (None -> lenient): {abstained}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
