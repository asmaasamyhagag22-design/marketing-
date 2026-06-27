"""Poster brand-safety audit trail (Evidence-Ledger Step 3c) — hermetic (MockCaller).

Proves the agency-facing PROOF object deterministically:
  * a grounded poster -> final_copy passes, every hard claim carries a REAL http source URL;
  * a softened fabrication -> recorded in `remediation` as HANDLED (not shown as sourced in
    final_copy, not hidden), and the shipped copy is clean;
  * a dropped fabricated chip -> recorded as 'dropped';
  * the artifact states its own SCOPING (covered vs excluded surfaces — reel is excluded).
"""
from __future__ import annotations

import json

from poster.concept import _ConceptResponse, build_creative_concept
from poster.audit import build_poster_audit
from business_profile.llm.caller import MockCaller


_ABOUT = "https://digilians.eg/about"


def _ef(value, quote, url):
    return {"value": value, "evidence": [{"block_id": "b", "page_url": url, "quote": quote,
            "extractor": "llm"}], "confidence": "high", "source_type": "extracted"}


# Arabic brand: 'الرواد' (pioneer/first) + '5000' (number) ARE sourced (real page_urls);
# nothing about 'الأكبر' (largest), '1850', or 'معتمد' (certification).
_AR = {
    "name": _ef("ديجيليانس", "ديجيليانس", "https://digilians.eg/"),
    "languages": ["ar"],
    "tagline": _ef("الرواد الرقميون", "الرواد الرقميون", _ABOUT),
    "description": _ef("ندرّب 5000 شاب سنويًا في البرمجة", "ندرّب 5000 شاب سنويًا في البرمجة", _ABOUT),
    "offerings": [],
}


def _resp(**kw) -> _ConceptResponse:
    base = dict(
        audience="شباب", single_message="رسالة", core_benefit="مهارة", emotional_tone="طموح",
        visual_idea="youth coding under warm light",
        proof_points=["تدريب عملي"], headline="روّاد الرقمنة",
        subheadline="ندرّب 5000 شاب", cta="سجّل الآن",
    )
    base.update(kw)
    return _ConceptResponse(**base)


def _claims(audit) -> list[dict]:
    return [cl for f in audit["final_copy"]["fields"] for cl in f["claims"]]


def test_grounded_poster_audit_has_real_source_urls_and_scoping():
    concept = build_creative_concept(
        _AR, caller=MockCaller({"poster_concept_brief": _resp()}), enforce_grounding=True)
    audit = build_poster_audit(_AR, concept)

    assert audit["final_copy"]["passes"] is True
    claims = _claims(audit)
    assert claims, "expected at least one hard claim (روّاد / 5000) in the shipped copy"
    assert all(c["sourced"] for c in claims)
    # REAL source URLs (the scraped page_url), not placeholders.
    assert all((c["source_url"] or "").startswith("http") for c in claims)
    assert any(c["source_url"] == _ABOUT for c in claims)
    assert all(c["source_tier"] == "brand" for c in claims)
    # Explicit scoping in the artifact itself; the reel is excluded.
    assert "reel" in audit["coverage"]["excluded_surfaces"]
    assert audit["coverage"]["covered_surfaces"]
    assert audit["remediated"] is False


def test_softened_fabrication_is_recorded_as_handled_not_sourced_not_hidden():
    # The mock returns the same fabricated headline every retry -> softened_to_fallback.
    bad = _resp(headline="الأكبر منذ 1850", subheadline="ندرّب 5000 شاب")
    concept = build_creative_concept(
        _AR, caller=MockCaller({"poster_concept_brief": bad}),
        enforce_grounding=True, max_retries=1)
    audit = build_poster_audit(_AR, concept)

    # 1) The gate WORKED and it is visible: remediation records the caught claim, handled.
    assert audit["remediated"] is True
    rem = audit["remediation"]
    assert any(r["field"] == "headline" for r in rem)
    assert {r["action"] for r in rem} & {"softened", "softened_to_fallback"}
    caught = next(r for r in rem if r["field"] == "headline")
    assert "1850" in caught["original_text"]                  # not hidden — the catch is shown
    assert "largest" in caught["unsourced_claims"] or "number" in caught["unsourced_claims"]

    # 2) The fabricated claim is NEVER presented as sourced in the shipped-copy trail.
    flat = json.dumps(audit["final_copy"], ensure_ascii=False)
    assert "1850" not in flat
    assert all(c["sourced"] for c in _claims(audit))          # only real claims remain
    assert audit["final_copy"]["passes"] is True              # shipped copy is clean


def test_fabricated_chip_is_recorded_as_dropped():
    resp = _resp(proof_points=["تدريب عملي", "شهادة معتمدة دوليًا"])  # 2nd chip = unsourced cert
    concept = build_creative_concept(
        _AR, caller=MockCaller({"poster_concept_brief": resp}),
        enforce_grounding=True, max_retries=0)
    audit = build_poster_audit(_AR, concept)

    dropped = [r for r in audit["remediation"] if r["action"] == "dropped"]
    assert dropped and any("معتمدة" in r["original_text"] for r in dropped)
    # The dropped chip is not in the shipped copy.
    assert all("معتمدة" not in (f["text"] or "") for f in audit["final_copy"]["fields"])
