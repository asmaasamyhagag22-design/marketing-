"""brand_research/pick_angle Evidence-Ledger gate — hermetic.

Asserts the gate has ZERO false positives (grounded angles kept) and ZERO false negatives
(fabricated angles dropped) over the curated AR+EN gray-case set, plus the source-tier
reputability rule and backward compatibility (no ledger -> old behaviour).
"""
from __future__ import annotations

from grounding.ledger import EvidenceLedger
from grounding.measure_step3 import GRAY_CASES, evaluate_gray_cases, _AR, _fact, _REPUTABLE, _JUNK
from poster.brand_research import BrandAngle, BrandResearch, pick_angle


def test_gray_case_set_has_no_false_positives_or_negatives():
    res = evaluate_gray_cases()
    bad = [r for r in res["rows"] if r["verdict"] != "ok"]
    assert res["fp"] == 0 and res["fn"] == 0, f"matcher errors: {bad}"
    assert res["total"] >= 15  # keep the set meaningfully broad


def test_arabic_inflected_superlative_is_not_a_false_positive():
    # 'روّاد' must resolve against the tagline 'الرواد' (same group, different inflection).
    led = EvidenceLedger.from_profile(_AR)
    head, _sub, prov = pick_angle(
        BrandResearch(used=True, angles=[BrandAngle(headline="روّاد التحول الرقمي")]),
        "fallback", variation=0, ledger=led)
    assert head == "روّاد التحول الرقمي"


def test_fabricated_certification_is_dropped_award_does_not_source_it():
    # The brand won an AWARD ('جائزة') but holds no CERTIFICATION — a fabricated 'معتمد ISO'
    # must NOT resolve via the award (the credential split). Gate -> verbatim fallback.
    led = EvidenceLedger.from_profile(_AR)
    head, _sub, prov = pick_angle(
        BrandResearch(used=True, angles=[BrandAngle(headline="تدريب معتمد دوليًا ISO",
                                                    asserts_hard_fact=True)]),
        "fallback line", variation=0, ledger=led)
    assert head == "fallback line" and prov == "profile"


def test_web_claim_from_reputable_source_is_kept_but_junk_is_dropped():
    claim = "الأكبر في الشرق الأوسط"
    led_rep = EvidenceLedger.from_profile(_AR, research={"facts": _fact(claim, _REPUTABLE)})
    led_junk = EvidenceLedger.from_profile(_AR, research={"facts": _fact(claim, _JUNK)})
    rep = pick_angle(BrandResearch(used=True, angles=[BrandAngle(headline=claim)]),
                     "fb", variation=0, ledger=led_rep)[0]
    junk = pick_angle(BrandResearch(used=True, angles=[BrandAngle(headline=claim)]),
                      "fb", variation=0, ledger=led_junk)[0]
    assert rep == claim           # reputable news snippet -> kept
    assert junk == "fb"           # aggregator snippet -> dropped to fallback


def test_no_ledger_keeps_legacy_behaviour():
    # Without a ledger, pick_angle behaves exactly as before (no evidence check).
    research = BrandResearch(used=True, angles=[
        BrandAngle(headline="الأكبر في الشرق الأوسط", grounded_in="profile",
                   asserts_hard_fact=False)])
    head, _sub, _prov = pick_angle(research, "fb", variation=0)
    assert head == "الأكبر في الشرق الأوسط"   # not dropped (gate off)
