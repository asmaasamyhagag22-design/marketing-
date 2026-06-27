"""Evidence Ledger — Step 3b (strategy/build_strategy gate): FALSE-POSITIVE/NEGATIVE set.

The LAST fabrication surface: a content-calendar HOOK becomes a poster/reel headline (via
`headline_override`, which skips the research path), so an unsourced hook ("ISO certified",
"#1 in Egypt", "since 1990") can ride straight onto a creative — and the calendar itself is
a client-facing deliverable. This module measures the gate predicate (`_hook_is_grounded`)
BEFORE it is wired into `build_strategy` live.

Calendar hooks are SHORTER and MORE METAPHORICAL than poster copy, and Arabic inflection
makes a grounded superlative easy to mis-match — so the poster/pick_angle "0 false
positives" does NOT transfer. This is a curated, DETERMINISTIC (no network, no LLM) gray-case
set: grounded claims phrased differently (must be KEPT) vs fabricated ones (must be DROPPED),
AR + EN, with special weight on RELATIVE-TIME claims ("منذ 1990", "خبرة 30 سنة") — these test
matcher PRECISION, not just policy: the SAME kind of claim must be KEPT when its specific
value is in the evidence (founding year / experience) and DROPPED when a different value of
the same kind is fabricated.

`evaluate_gray_cases()` is the single source of truth — `tests/test_strategy_grounding.py`
asserts FP==0 and FN==0 over it; `main()` prints the breakdown and the gate-off vs gate-on
binary.

Run:  python -m grounding.measure_step3b
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

from grounding.ledger import EvidenceLedger
from strategy.builder import _hook_is_grounded


def _ef(value: str, quote: str, url: str = "https://brand.example/p") -> dict:
    return {"value": value, "evidence": [{"block_id": "b", "page_url": url, "quote": quote,
            "extractor": "llm"}], "confidence": "high", "source_type": "extracted"}


# AR brand evidence: pioneer ('الرواد'), best ('أفضل'), a number (5000), a FOUNDING YEAR
# (1990), EXPERIENCE (30 years), an AWARD ('جائزة') — but NO certification, NO 'largest',
# NO 'only', and specifically NOT the years 1985 nor "50 years".
_AR = {
    "name": _ef("ديجيليانس", "ديجيليانس"),
    "languages": ["ar"],
    "tagline": _ef("الرواد الرقميون", "الرواد الرقميون"),
    "description": _ef("ندرّب 5000 شاب سنويًا في البرمجة", "ندرّب 5000 شاب سنويًا في البرمجة"),
    "value_propositions": [_ef("نقدّم أفضل تدريب تقني", "نقدّم أفضل تدريب تقني")],
    "trust_signals": [
        _ef("تأسست عام 1990", "تأسست عام 1990"),
        _ef("بخبرة 30 عامًا في التدريب", "بخبرة 30 عامًا في التدريب"),
        _ef("حاصلون على جائزة أفضل مبادرة شبابية", "جائزة أفضل مبادرة شبابية"),
    ],
}
# EN brand evidence: leading (first), a number (5000), a FOUNDING YEAR (1995), EXPERIENCE
# (25 years), an AWARD — but NO certification, NO 'largest', NO 'only', NOT 1980 nor 9001.
_EN = {
    "name": _ef("Acme Academy", "Acme Academy"),
    "languages": ["en"],
    "description": _ef("We train 5000 engineers annually", "We train 5000 engineers annually"),
    "value_propositions": [_ef("the leading coding school in the region",
                               "the leading coding school in the region")],
    "trust_signals": [
        _ef("Established in 1995", "Established in 1995"),
        _ef("25 years of hands-on experience", "25 years of hands-on experience"),
        _ef("an award-winning bootcamp", "an award-winning bootcamp"),
    ],
}


# (label, profile, hook_text, expected_keep)
GRAY_CASES = [
    # ---- grounded / rephrased -> MUST be KEPT (false-positive guard) ----
    ("AR pioneer rephrase",        _AR, "روّاد التحول الرقمي", True),
    ("AR best rephrase",           _AR, "الأفضل في التدريب التقني", True),
    ("AR number grounded",         _AR, "5000 خريج سنويًا", True),
    ("AR founding-year grounded",  _AR, "نخدمكم منذ 1990", True),     # 1990 is in the evidence
    ("AR experience grounded",     _AR, "بخبرة 30 سنة في المجال", True),  # 30 yrs is in the evidence
    ("AR award grounded",          _AR, "حاصلون على جائزة التميز", True),
    ("AR pure paraphrase",         _AR, "ابدأ رحلتك الرقمية معنا اليوم", True),
    ("EN leading rephrase",        _EN, "The leading coding academy", True),
    ("EN number grounded",         _EN, "5000 engineers trained", True),
    ("EN founding-year grounded",  _EN, "Serving since 1995", True),  # 1995 is in the evidence
    ("EN experience grounded",     _EN, "25 years of expertise", True),  # 25 yrs is in the evidence
    ("EN award grounded",          _EN, "Award-winning training", True),
    ("EN pure paraphrase",         _EN, "Built for builders", True),
    # ---- fabricated -> MUST be DROPPED (false-negative guard) ----
    ("AR fabricated largest",      _AR, "الأكبر في الشرق الأوسط", False),
    ("AR fabricated only",         _AR, "المعهد الوحيد في مصر", False),
    ("AR fabricated cert (ISO)",   _AR, "تدريب معتمد دوليًا ISO", False),   # award != certification
    ("AR fabricated WRONG year",   _AR, "نخدمكم منذ 1985", False),   # 1990 sourced, 1985 is NOT
    ("AR fabricated WRONG exp",    _AR, "بخبرة 50 سنة", False),       # 30 yrs sourced, 50 is NOT
    ("EN fabricated cert+year",    _EN, "ISO 9001 certified since 1980", False),
    ("EN fabricated largest",      _EN, "The largest bootcamp in Africa", False),
    ("EN fabricated only",         _EN, "The only certified academy", False),
    # ---- superlative class: NEW coverage (was a hole) -> fabricated MUST DROP ----
    ("AR fabricated fastest",      _AR, "الأسرع في السوق", False),     # أسرع not sourced
    ("AR fabricated cheapest",     _AR, "الأرخص في مصر", False),       # أرخص not sourced
    ("EN fabricated fastest",      _EN, "The fastest network in the country", False),
    # ---- AR precision FP-guards: superlative-SHAPED words that are NOT elatives -> KEEP ----
    ("AR noun الأساس (foundation)", _AR, "نبني على الأساس الصحيح", True),   # not 'أساس' != elative
    ("AR noun الأحداث (events)",    _AR, "تابع آخر الأحداث معنا", True),     # 'الأحداث' != 'أحدث'
    ("AR base adjective راقية",     _AR, "تجربة راقية تستحقها", True),       # 'راقية' != elative 'أرقى'
]


def evaluate_gray_cases() -> dict:
    fp, fn, rows = 0, 0, []
    for label, profile, hook, expected in GRAY_CASES:
        ledger = EvidenceLedger.from_profile(profile)
        kept = _hook_is_grounded(hook, ledger)
        verdict = "ok"
        if kept and not expected:
            fn += 1; verdict = "FALSE-NEGATIVE (fabricated KEPT)"
        elif not kept and expected:
            fp += 1; verdict = "FALSE-POSITIVE (grounded DROPPED)"
        rows.append({"label": label, "hook": hook, "expected_keep": expected,
                     "kept": kept, "verdict": verdict})
    return {"fp": fp, "fn": fn, "total": len(GRAY_CASES), "rows": rows}


def main() -> int:
    res = evaluate_gray_cases()
    print("Step 3b — strategy hook Evidence-Ledger gate: gray-case evaluation\n" + "=" * 64)
    for r in res["rows"]:
        mark = "OK " if r["verdict"] == "ok" else "!! "
        keep = "KEEP" if r["kept"] else "DROP"
        print(f"  {mark}[{keep:4}] {r['label']:26} :: {r['hook']}")
        if r["verdict"] != "ok":
            print(f"        -> {r['verdict']}")
    print("=" * 64)
    kept_fabricated = sum(1 for r in res["rows"] if not r["expected_keep"] and r["kept"])
    print(f"cases={res['total']}  false_positives={res['fp']}  false_negatives={res['fn']}")
    print("\nBinary (what we stand behind, not a rate):")
    print(f"  gate OFF -> {sum(1 for r in res['rows'] if not r['expected_keep'])} fabricated hooks "
          f"would ship as-is (the LLM can emit any of them).")
    print(f"  gate ON  -> {kept_fabricated} fabricated hooks survive; "
          f"{res['fp']} grounded hooks wrongly dropped.")
    return 0 if (res["fp"] == 0 and res["fn"] == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
