"""strategy/build_strategy hook Evidence-Ledger gate — hermetic (no network, no LLM).

Asserts the gate predicate has ZERO false positives (grounded hooks kept) and ZERO false
negatives (fabricated hooks dropped) over the curated AR+EN gray-case set, with explicit
coverage of RELATIVE-TIME matcher precision (a year/experience claim is kept only when its
specific value is in the evidence) and the award != certification credential split.
"""
from __future__ import annotations

from grounding.ledger import EvidenceLedger
from grounding.measure_step3b import GRAY_CASES, evaluate_gray_cases, _AR, _EN
from strategy.builder import _hook_is_grounded


def test_gray_case_set_has_no_false_positives_or_negatives():
    res = evaluate_gray_cases()
    bad = [r for r in res["rows"] if r["verdict"] != "ok"]
    assert res["fp"] == 0 and res["fn"] == 0, f"matcher errors: {bad}"
    assert res["total"] >= 18  # keep the set meaningfully broad


def test_relative_time_matcher_precision_year():
    # Same KIND of claim, different value: the sourced founding year is KEPT, a fabricated
    # one of the same shape is DROPPED. This pins the number matcher, not just the policy.
    led = EvidenceLedger.from_profile(_AR)   # evidence has 'تأسست عام 1990'
    assert _hook_is_grounded("نخدمكم منذ 1990", led) is True      # 1990 sourced
    assert _hook_is_grounded("نخدمكم منذ 1985", led) is False     # 1985 fabricated


def test_relative_time_matcher_precision_experience():
    led = EvidenceLedger.from_profile(_AR)   # evidence has 'بخبرة 30 عامًا'
    assert _hook_is_grounded("بخبرة 30 سنة في المجال", led) is True   # 30 yrs sourced
    assert _hook_is_grounded("بخبرة 50 سنة", led) is False            # 50 yrs fabricated


def test_award_does_not_source_a_certification_claim():
    # The brand won an AWARD ('جائزة') but holds no CERTIFICATION; a fabricated 'معتمد ISO'
    # must NOT resolve via the award (the credential split).
    led = EvidenceLedger.from_profile(_AR)
    assert _hook_is_grounded("حاصلون على جائزة التميز", led) is True
    assert _hook_is_grounded("تدريب معتمد دوليًا ISO", led) is False


def test_pure_paraphrase_always_passes():
    led_ar = EvidenceLedger.from_profile(_AR)
    led_en = EvidenceLedger.from_profile(_EN)
    assert _hook_is_grounded("ابدأ رحلتك الرقمية معنا اليوم", led_ar) is True
    assert _hook_is_grounded("Built for builders", led_en) is True


def test_fabricated_superlatives_are_dropped_en():
    led = EvidenceLedger.from_profile(_EN)   # has 'leading' (first) + award, but no largest/only/cert
    assert _hook_is_grounded("The leading coding academy", led) is True
    assert _hook_is_grounded("The largest bootcamp in Africa", led) is False
    assert _hook_is_grounded("The only certified academy", led) is False


def test_every_gray_case_label_is_covered():
    # Guard against a silently dropped case (the set is the measurement of record).
    assert len(GRAY_CASES) == len({c[0] for c in GRAY_CASES})  # unique labels


# ---- live wiring: build_strategy(ledger=...) drop-to-grounded (deterministic) ----

def test_build_strategy_blanks_fabricated_hook_and_angle_keeps_grounded():
    from strategy.builder import _PlanItem, _PlanResponse, build_strategy
    from business_profile.llm.caller import MockCaller
    plan = _PlanResponse(items=[
        _PlanItem(day_offset=0, platform="instagram", content_type="post",
                  topic="تدريب البرمجة", angle="الأكبر في الشرق الأوسط",   # fabricated 'largest'
                  hook="المعهد الوحيد المعتمد دوليًا"),                      # fabricated only+cert
        _PlanItem(day_offset=1, platform="tiktok", content_type="reel",
                  topic="مبادرة شبابية", angle="ابدأ رحلتك معنا",           # paraphrase (no claim)
                  hook="الأفضل في التدريب التقني"),                         # grounded ('best' sourced)
    ])
    led = EvidenceLedger.from_profile(_AR)
    cal = build_strategy(_AR, MockCaller({"content_strategy": plan}),
                         days=14, start_date="2026-06-20", ledger=led)
    by_topic = {i.topic: i for i in cal.items}
    fab = by_topic["تدريب البرمجة"]
    assert fab.hook == "" and fab.angle == ""          # fabricated hook+angle blanked
    assert fab.topic == "تدريب البرمجة"                 # real topic kept (headline falls back to it)
    good = by_topic["مبادرة شبابية"]
    assert good.hook == "الأفضل في التدريب التقني"       # grounded hook untouched
    assert good.angle == "ابدأ رحلتك معنا"               # paraphrase angle untouched


def test_blanked_item_records_remediation_not_silent():
    # The blank must be VISIBLE: the item shows its hook/angle was fabricated and removed,
    # and that it now runs on its sourced topic — not that the hook silently vanished.
    from strategy.builder import _PlanItem, _PlanResponse, build_strategy
    from business_profile.llm.caller import MockCaller
    plan = _PlanResponse(items=[
        _PlanItem(day_offset=0, platform="instagram", content_type="post",
                  topic="تدريب البرمجة", angle="الأكبر في الشرق الأوسط",      # fabricated
                  hook="المعهد الوحيد المعتمد دوليًا"),                         # fabricated
        _PlanItem(day_offset=1, platform="tiktok", content_type="reel",
                  topic="مبادرة شبابية", angle="ابدأ رحلتك معنا",              # paraphrase
                  hook="الأفضل في التدريب التقني"),                            # grounded
    ])
    cal = build_strategy(_AR, MockCaller({"content_strategy": plan}),
                         days=14, start_date="2026-06-20", ledger=EvidenceLedger.from_profile(_AR))
    by_topic = {i.topic: i for i in cal.items}
    fab = by_topic["تدريب البرمجة"]
    assert fab.hook == "" and fab.angle == ""               # blank result unchanged
    assert {r["field"] for r in fab.remediation} == {"hook", "angle"}
    hook_rec = next(r for r in fab.remediation if r["field"] == "hook")
    assert hook_rec["original_text"] == "المعهد الوحيد المعتمد دوليًا"   # not hidden
    assert hook_rec["action"] == "blanked" and hook_rec["unsourced_claims"]
    assert fab.topic == "تدريب البرمجة"                     # runs on its sourced topic
    good = by_topic["مبادرة شبابية"]
    assert good.hook == "الأفضل في التدريب التقني" and good.remediation == []  # grounded: nothing recorded


def test_build_strategy_without_ledger_is_unchanged():
    from strategy.builder import _PlanItem, _PlanResponse, build_strategy
    from business_profile.llm.caller import MockCaller
    plan = _PlanResponse(items=[
        _PlanItem(day_offset=0, platform="instagram", content_type="post",
                  topic="تدريب", angle="", hook="المعهد الوحيد المعتمد دوليًا")])
    cal = build_strategy(_AR, MockCaller({"content_strategy": plan}),
                         days=7, start_date="2026-06-20")     # no ledger -> gate off
    assert cal.items[0].hook == "المعهد الوحيد المعتمد دوليًا"  # unchanged (backward compatible)
