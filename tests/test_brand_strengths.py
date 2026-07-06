"""Brand-level SWOT Strengths (competitor/brand_signals.py + synthesize_swot profile=).

Origin (owner): the SWOT was "all page attributes, not brand-level" — Strengths read "Number of
CTAs: 3", "Social links: 20" while the grounded profile carried the real story (heritage,
craftsmanship, 18kt gold, "Loved by 17k+ customers"). Now the SWOT LEADS with brand-level
strengths mined from value_propositions + strong trust_signals, each Ledger-gated (no invented
facts), with the mechanical gaps kept as a secondary signal. Hermetic: no network, no LLM.
"""
from __future__ import annotations

import dataclasses

from competitor.brand_signals import strengths_from_profile
from competitor.matrix import build_matrix
from competitor.swot import synthesize_swot
from grounding import EvidenceLedger


def _ev(q):
    return [{"quote": q, "page_url": "https://brand.example/"}]


def _profile():
    return {
        "name": {"value": "Heritage Co"},
        "value_propositions": [
            {"value": "Handcrafted heritage jewelry rooted in tradition",
             "evidence": _ev("Handcrafted heritage jewelry rooted in tradition")},
            {"value": "18kt gold and champagne diamonds",
             "evidence": _ev("18kt gold and champagne diamonds")},
        ],
        "trust_signals": [
            {"value": "Loved by 12k+ customers", "evidence": _ev("Loved by 12k+ customers")},
            {"value": "Secure Payments", "evidence": _ev("Secure Payments")},   # generic boilerplate
        ],
        "existing_ctas": [{"value": "Shop now"}],
    }


def test_value_props_and_strong_trust_become_grounded_strengths():
    p = _profile()
    ledger = EvidenceLedger.from_profile(p)
    strengths = strengths_from_profile(p, ledger)
    texts = [s.text for s in strengths]
    # brand-level value props surface (the SWOT's "story", not page attributes)
    assert "Handcrafted heritage jewelry rooted in tradition" in texts
    assert "18kt gold and champagne diamonds" in texts
    # a proof-carrying trust signal surfaces; generic checkout boilerplate is filtered out
    assert "Loved by 12k+ customers" in texts
    assert "Secure Payments" not in texts
    # provenance + honest tier
    for s in strengths:
        assert s.citation[0] == "your profile" and s.citation[1] in ("value_propositions", "trust_signals")
        assert s.claim_strength == "internally_supported"
    # grounding integrity: every emitted line passes the same Ledger gate the moat uses
    for s in strengths:
        assert all(v.sourced for v in ledger.audit_text(s.text))


def test_gate_drops_a_line_whose_hard_claim_is_unsourced():
    # A line with a NUMBER the ledger can't back must be dropped (fail-closed); a pure-paraphrase
    # line with no hard claim passes even against an empty ledger.
    p = {"value_propositions": [
        {"value": "Handmade with care"},                 # no hard claim -> passes
        {"value": "Trusted by 500000 clients worldwide"},  # 500000 unsourced -> dropped
    ]}
    empty = EvidenceLedger.from_profile({})
    texts = [s.text for s in strengths_from_profile(p, empty)]
    assert "Handmade with care" in texts
    assert "Trusted by 500000 clients worldwide" not in texts


def test_synthesize_swot_leads_with_brand_strengths_and_is_regression_safe():
    p = _profile()
    m = build_matrix(p, [])                               # no peers -> standalone/own-site path
    before = synthesize_swot(m)                           # profile=None (today's behavior)
    after = synthesize_swot(m, profile=p)                 # brand-level strengths mined + prepended
    after_texts = [s.text for s in after.strengths]
    before_texts = [s.text for s in before.strengths]

    # brand-level strengths are present AFTER and absent BEFORE
    assert "18kt gold and champagne diamonds" in after_texts
    assert "18kt gold and champagne diamonds" not in before_texts
    # and they LEAD (prepended before any mechanical own-site strength)
    assert after.strengths[0].citation[0] == "your profile"
    # regression: profile=None output is byte-identical to pre-change
    assert dataclasses.asdict(synthesize_swot(m)) == dataclasses.asdict(before)


def test_no_profile_or_empty_profile_changes_nothing():
    p = _profile()
    m = build_matrix(p, [])
    assert dataclasses.asdict(synthesize_swot(m, profile=None)) == dataclasses.asdict(synthesize_swot(m))
    assert strengths_from_profile({}, EvidenceLedger.from_profile({})) == []
