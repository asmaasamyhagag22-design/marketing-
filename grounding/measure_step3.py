"""Evidence Ledger — Step 3 (brand_research/pick_angle gate): FALSE-POSITIVE/NEGATIVE set.

Ad angles are more metaphorical than poster copy — and Arabic inflection makes a grounded
superlative easy to mis-match — so the poster's "0 false positives" does NOT transfer. This
is a curated, DETERMINISTIC (no network) gray-case set: grounded claims phrased differently
(must be KEPT) vs fabricated ones (must be DROPPED), AR + EN, including the web-source
reputability split (a snippet from a junk aggregator is not proof).

`evaluate_gray_cases()` is the single source of truth — `tests/test_brand_research_grounding.py`
asserts FP==0 and FN==0 over it; `main()` prints the breakdown.

Run:  python -m grounding.measure_step3
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

from grounding.ledger import EvidenceLedger
from poster.brand_research import BrandAngle, _ledger_keeps_angle


def _ef(value: str, quote: str, url: str = "https://brand.example/p") -> dict:
    return {"value": value, "evidence": [{"block_id": "b", "page_url": url, "quote": quote,
            "extractor": "llm"}], "confidence": "high", "source_type": "extracted"}


# Brand evidence: pioneer ('الرواد'), best ('أفضل'), a number (5000), an AWARD ('جائزة') —
# but NO certification, NO 'largest', NO 'only', NO year.
_AR = {
    "name": _ef("ديجيليانس", "ديجيليانس"),
    "languages": ["ar"],
    "tagline": _ef("الرواد الرقميون", "الرواد الرقميون"),
    "description": _ef("ندرّب 5000 شاب سنويًا في البرمجة", "ندرّب 5000 شاب سنويًا في البرمجة"),
    "value_propositions": [_ef("نقدّم أفضل تدريب تقني", "نقدّم أفضل تدريب تقني")],
    "trust_signals": [_ef("حاصلون على جائزة أفضل مبادرة شبابية", "جائزة أفضل مبادرة شبابية")],
}
_EN = {
    "name": _ef("Acme", "Acme"),
    "languages": ["en"],
    "description": _ef("We train 5000 engineers annually", "We train 5000 engineers annually"),
    "value_propositions": [_ef("the leading coding school in the region",
                               "the leading coding school in the region")],
    "trust_signals": [_ef("an award-winning bootcamp", "an award-winning bootcamp")],
}

_REPUTABLE = "https://www.reuters.com/world/egypt-digilians"
_JUNK = "https://www.g2.com/products/digilians"   # g2.com is in the aggregator denylist


def _fact(text: str, url: str) -> list[dict]:
    return [{"text": text, "source_url": url}]


# (label, profile, research_facts, angle_text, expected_keep)
GRAY_CASES = [
    # --- grounded, phrased differently -> MUST be kept (false-positive guard) ---
    ("AR pioneer rephrase",      _AR, None, "روّاد التحول الرقمي", True),
    ("AR best rephrase",         _AR, None, "الأفضل في التدريب التقني", True),
    ("AR number rephrase",       _AR, None, "ندرّب 5000 خريج سنويًا", True),
    ("AR award grounded",        _AR, None, "حاصلون على جائزة التميز", True),
    ("AR pure paraphrase",       _AR, None, "ابدأ رحلتك الرقمية معنا", True),
    ("EN leading rephrase",      _EN, None, "The leading coding academy", True),
    ("EN award grounded",        _EN, None, "Award-winning training", True),
    ("EN number grounded",       _EN, None, "5000 engineers trained", True),
    ("EN pure paraphrase",       _EN, None, "Built for builders", True),
    # --- fabricated -> MUST be dropped (false-negative guard) ---
    ("AR fabricated largest",    _AR, None, "الأكبر في الشرق الأوسط", False),
    ("AR fabricated only+cert",  _AR, None, "المعهد الوحيد المعتمد دوليًا", False),
    ("AR fabricated cert (ISO)", _AR, None, "تدريب معتمد دوليًا ISO", False),  # award != certification
    ("AR fabricated year",       _AR, None, "نخدمكم منذ 1990", False),
    ("EN fabricated cert+year",  _EN, None, "ISO 9001 certified since 1990", False),
    ("EN fabricated certifier",  _EN, None, "Certified by Harvard", False),
    # --- web-source reputability (a claim sourced ONLY by a snippet) ---
    ("AR largest @reputable",    _AR, _fact("ديجيليانس الأكبر في الشرق الأوسط", _REPUTABLE),
                                 "الأكبر في الشرق الأوسط", True),
    ("AR largest @junk",         _AR, _fact("ديجيليانس الأكبر في الشرق الأوسط", _JUNK),
                                 "الأكبر في الشرق الأوسط", False),
]


def evaluate_gray_cases() -> dict:
    fp, fn, rows = 0, 0, []
    for label, profile, facts, angle_text, expected in GRAY_CASES:
        ledger = EvidenceLedger.from_profile(profile, research={"facts": facts or []})
        angle = BrandAngle(headline=angle_text, asserts_hard_fact=True,
                           grounded_in=(facts[0]["source_url"] if facts else "profile"))
        kept = _ledger_keeps_angle(angle, ledger)
        verdict = "ok"
        if kept and not expected:
            fn += 1; verdict = "FALSE-NEGATIVE (fabricated KEPT)"
        elif not kept and expected:
            fp += 1; verdict = "FALSE-POSITIVE (grounded DROPPED)"
        rows.append({"label": label, "angle": angle_text, "expected_keep": expected,
                     "kept": kept, "verdict": verdict})
    return {"fp": fp, "fn": fn, "total": len(GRAY_CASES), "rows": rows}


def main() -> int:
    res = evaluate_gray_cases()
    print("Step 3 — pick_angle Evidence-Ledger gate: gray-case evaluation\n" + "=" * 60)
    for r in res["rows"]:
        mark = "OK " if r["verdict"] == "ok" else "!! "
        keep = "KEEP" if r["kept"] else "DROP"
        print(f"  {mark}[{keep:4}] {r['label']:24} :: {r['angle']}")
        if r["verdict"] != "ok":
            print(f"        -> {r['verdict']}")
    print("=" * 60)
    print(f"cases={res['total']}  false_positives={res['fp']}  false_negatives={res['fn']}")
    return 0 if (res["fp"] == 0 and res["fn"] == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
