"""Concept grounding gate (Evidence Ledger, enforce_grounding=True) — hermetic.

Proves the BLOCKING behaviour deterministically (MockCaller, no network): a fabricated
falsifiable claim is never shipped (regenerate-then-grounded-fallback), grounded copy
passes untouched, subjective puffery passes, and the gate is OFF by default.
"""
from __future__ import annotations

from poster.concept import CreativeConcept, _ConceptResponse, build_creative_concept
from business_profile.llm.caller import MockCaller
from grounding import EvidenceLedger


def _ef(value, quote, url="https://brand.example/p", conf="high"):
    return {"value": value, "evidence": [{"block_id": "b", "page_url": url, "quote": quote,
            "extractor": "llm"}], "confidence": conf, "source_type": "extracted"}


# An Arabic brand whose evidence supports "رواد" (pioneer) + "5000" but NOTHING about
# "الأكبر" (largest) or "1850".
_AR_GROUNDED = {
    "name": _ef("Digilians", "Digilians"),
    "languages": ["ar"],
    "tagline": _ef("الرواد الرقميون", "الرواد الرقميون"),
    "description": _ef("ندرّب 5000 شاب سنويًا في البرمجة", "ندرّب 5000 شاب سنويًا في البرمجة"),
    "offerings": [],
}


def _resp(**kw) -> _ConceptResponse:
    base = dict(
        audience="شباب", single_message="رسالة", core_benefit="مهارة", emotional_tone="طموح",
        visual_idea="youth coding under warm light",
        proof_points=["تدريب عملي", "شهادة معتمدة"], headline="روّاد الرقمنة",
        subheadline="ندرّب 5000 شاب", cta="سجّل الآن",
    )
    base.update(kw)
    return _ConceptResponse(**base)


def _has_unsourced(profile: dict, c: CreativeConcept) -> bool:
    led = EvidenceLedger.from_profile(profile)
    fields = [c.headline, c.subheadline, c.cta, *c.proof_points]
    return any(not v.sourced for f in fields for v in led.audit_text(f or ""))


def test_grounded_copy_passes_untouched():
    # headline 'روّاد' resolves via tagline 'الرواد'; sub '5000' via description.
    resp = _resp(proof_points=["تدريب عملي"])  # subjective puffery chip, no claim
    c = build_creative_concept(_AR_GROUNDED,
                               caller=MockCaller({"poster_concept_brief": resp}),
                               enforce_grounding=True)
    assert c.headline == "روّاد الرقمنة"
    assert not _has_unsourced(_AR_GROUNDED, c)


def test_fabricated_superlative_and_number_never_ship():
    # 'الأكبر' (largest) + '1850' are nowhere in the evidence. The mock returns the same
    # fabricated copy each retry -> the gate falls back to grounded copy (never ships it).
    bad = _resp(headline="الأكبر منذ 1850", subheadline="الأقوى في مصر")
    c = build_creative_concept(_AR_GROUNDED,
                               caller=MockCaller({"poster_concept_brief": bad}),
                               enforce_grounding=True, max_retries=1)
    assert c.headline != "الأكبر منذ 1850"
    assert "1850" not in (c.headline + c.subheadline)
    assert not _has_unsourced(_AR_GROUNDED, c)
    assert "fallback" in (c.note or "")


def test_fabricated_credential_chip_is_dropped():
    # 'شهادة معتمدة' (certified) is unsupported -> the chip must not survive.
    resp = _resp(proof_points=["تدريب عملي", "شهادة معتمدة دوليًا"])
    c = build_creative_concept(_AR_GROUNDED,
                               caller=MockCaller({"poster_concept_brief": resp}),
                               enforce_grounding=True, max_retries=0)
    assert all("معتمدة" not in p for p in c.proof_points)


def test_subjective_puffery_passes():
    # 'تجربة راقية' asserts nothing checkable -> allowed (copy stays alive).
    resp = _resp(headline="تجربة راقية", subheadline="ندرّب 5000 شاب",
                 proof_points=["تدريب عملي"])
    c = build_creative_concept(_AR_GROUNDED,
                               caller=MockCaller({"poster_concept_brief": resp}),
                               enforce_grounding=True)
    assert c.headline == "تجربة راقية"


def test_gate_is_off_by_default():
    # Without enforce_grounding, the fabricated claim is NOT softened (existing contract).
    bad = _resp(headline="الأكبر منذ 1850")
    c = build_creative_concept(_AR_GROUNDED,
                               caller=MockCaller({"poster_concept_brief": bad}))
    assert c.headline == "الأكبر منذ 1850"
