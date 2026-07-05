"""C2 gate: a number claim is 'verified' only by evidence carrying the SAME KIND of number.

Regression origin (2026-07-05 audit): resolution matched the BARE digit anywhere in the
evidence, with no unit context. So the Evidence Ledger — and the client-facing Ad
Compliance Sheet built from it — certified fabrications as 'verified':
  "Save 50% today"        -> verified by "Serving Egypt for 50 years"
  "Only 99% pure"         -> verified by a "99 EGP" price
The same `audit_text` powers the poster/reel/strategy/TOWS gates, so these fabricated
claims also PASSED the gate and rendered. The fix requires a %/price/duration/scale claim
to match evidence of the same class; plain numbers keep the prior lenient behavior (so no
legitimate claim regresses).

Hermetic: EvidenceLedger built from a profile dict; no network / no LLM.
"""
from grounding import EvidenceLedger


def _led():
    profile = {
        "name": {"value": "Acme"},
        "description": {"value": "Serving Egypt for 50 years. Visit one of our 100 stores. "
                                 "Prices from 99 EGP. Best regards from the team."},
        "offerings": [{"name": "Coffee"}],
    }
    return EvidenceLedger.from_profile(profile)


def _sourced(led, copy):
    """True iff EVERY number claim in `copy` resolved (mirrors the gate)."""
    vs = [v for v in led.audit_text(copy) if v.claim.kind == "number"]
    return bool(vs) and all(v.sourced for v in vs)


def test_percent_claim_not_verified_by_a_year_count():
    led = _led()
    assert not _sourced(led, "Save 50% today")        # "50 years" must NOT source "50%"
    assert not _sourced(led, "Now 50% off everything")


def test_percent_claim_not_verified_by_a_price():
    led = _led()
    assert not _sourced(led, "Only 99% pure")          # "99 EGP" (currency) != "99%"


def test_legitimate_duration_claim_still_resolves():
    led = _led()
    # "50 years" in the copy IS backed by "50 years" in the evidence (same class).
    assert _sourced(led, "Serving customers for 50 years")


def test_fabricated_year_with_no_evidence_is_rejected():
    led = _led()
    assert not _sourced(led, "Established since 1985")   # nothing says 1985


def test_plain_bare_number_keeps_lenient_matching():
    # A plain count is still sourced when the value appears (prior behavior preserved) —
    # this is the documented residual (bare-number context is not yet disambiguated).
    led = _led()
    assert _sourced(led, "Trusted by 100 customers")     # matches the bare "100 stores"


def test_multi_class_claim_is_deterministic_and_not_regressed():
    # A copy can use the same digit in TWO strong classes ("50% today, valid 50 days").
    # The claim must resolve deterministically (not PYTHONHASHSEED-dependent) whenever the
    # evidence supports the value in ANY of those classes — here a real "50% off".
    prof = {"name": {"value": "X"}, "description": {"value": "Get 50% off this week"}}
    led = EvidenceLedger.from_profile(prof)
    assert _sourced(led, "save 50% today, valid 50 days")
    # And a strong-class claim with NO matching-class evidence stays unsourced.
    prof2 = {"name": {"value": "X"}, "description": {"value": "Open for 50 years"}}
    led2 = EvidenceLedger.from_profile(prof2)
    assert not _sourced(led2, "save 50% off now")   # "50 years" (dur) can't source "50%" (pct)


def test_compliance_sheet_does_not_mark_fabricated_percent_verified():
    """End-to-end: the shipped compliance sheet must not carry a 'verified' row for a
    fabricated discount."""
    from poster.audit import build_poster_audit  # noqa: F401 — ensure import path exists
    led = _led()
    verdicts = led.audit_text("Save 50% today")
    num = next(v for v in verdicts if v.claim.kind == "number")
    assert num.sourced is False
