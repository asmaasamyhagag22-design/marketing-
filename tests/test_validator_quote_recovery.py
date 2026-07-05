"""Validator quote-recovery gate (2026-07-05 finder lead).

The citation validator used to DISCARD an evidence item whenever its block_id was wrong,
even if the quoted text was verbatim in another real block — throwing away real, citable
evidence over a mis-attribution. Recovery now searches all blocks for the verbatim quote
and accepts with the corrected block_id (same substring strictness, plus a length floor so
a stop-word can't be laundered into a coincidental match). A quote that is in NO block is
still rejected (genuine fabrication).

Hermetic: pure function over a synthetic block lookup.
"""
from business_profile.llm.validator import (
    _BlockLookup, _recover_by_quote, _validate_evidence_item, RejectionCode,
)
from business_profile.schemas import LLMEvidenceRef


def _lookup():
    from business_profile.llm.validator import _normalize
    text = {
        "home_h1_0001": "Premium Foot Care in Cairo",
        "about_p_0001": "Founded in 2010, we serve patients across Cairo and Giza.",
        "svc_p_0003": "We offer diabetic foot screening and nail surgery.",
    }
    pages = {k: "https://x.com/" for k in text}
    return _BlockLookup(text, pages, {k: _normalize(v) for k, v in text.items()})


def test_recovers_quote_from_a_different_block():
    lookup = _lookup()
    rec = _recover_by_quote("diabetic foot screening", lookup)
    assert rec is not None
    bid, page, quote = rec
    assert bid == "svc_p_0003"


def test_wrong_block_id_but_quote_in_another_block_is_kept():
    lookup = _lookup()
    ref = LLMEvidenceRef(block_id="does_not_exist", quote="Founded in 2010")
    item, rej = _validate_evidence_item(ref, lookup)
    assert rej is None and item is not None
    assert item.block_id == "about_p_0001"


def test_right_block_id_but_quote_actually_in_another_block_is_kept():
    # LLM cited an existing block, but the quote lives in a DIFFERENT real block.
    lookup = _lookup()
    ref = LLMEvidenceRef(block_id="home_h1_0001", quote="nail surgery")
    item, rej = _validate_evidence_item(ref, lookup)
    assert rej is None and item is not None
    assert item.block_id == "svc_p_0003"


def test_quote_in_no_block_is_still_rejected():
    lookup = _lookup()
    ref = LLMEvidenceRef(block_id="whatever", quote="we cure everything overnight")
    item, rej = _validate_evidence_item(ref, lookup)
    assert item is None and rej is not None


def test_short_stopword_quote_is_not_recovered():
    # "in" appears in every block, but a 2-char stop word must not be laundered into a match.
    lookup = _lookup()
    assert _recover_by_quote("in", lookup) is None
    assert _recover_by_quote("we", lookup) is None
