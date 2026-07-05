# -*- coding: utf-8 -*-
"""Unsubstantiated-claim blacklist uses WORD-BOUNDARY matching, not raw substring (2026-07-05).

The substring test had two failure modes:
- FALSE-REJECT: "iso" matched inside poison / comparison / revision, and "healthy" inside
  "unhealthy" — dropping a real offering that never made the claim.
- LAUNDERING: an "ISO"/"organic" claim was treated as grounded when the cited quote merely
  CONTAINED the substring (e.g. "comparison" grounds "iso").

Hermetic: pure function over synthetic evidence items.
"""
from types import SimpleNamespace

from business_profile.llm.validator import _contains_blacklisted_claim as _chk


def _ev(*quotes):
    return [SimpleNamespace(quote=q) for q in quotes]


def test_substring_inside_a_real_word_does_not_flag():
    assert _chk("poison antidote", _ev("fish poison antidote")) is None       # not "iso"
    assert _chk("price comparison guide", _ev("a comparison guide")) is None  # not "iso"
    assert _chk("revision history", _ev("the revision history")) is None      # not "iso"
    assert _chk("unhealthy habits", _ev("avoid unhealthy habits")) is None    # not "healthy"
    assert _chk("inorganic chemistry", _ev("inorganic chemistry 101")) is None  # not "organic"


def test_whole_word_claim_without_grounding_is_flagged():
    assert _chk("halal beef", _ev("premium beef cuts")) == "halal"
    assert _chk("organic honey", _ev("pure honey")) == "organic"


def test_whole_word_claim_with_grounding_is_kept():
    assert _chk("halal beef", _ev("our halal beef")) is None
    assert _chk("organic honey", _ev("certified organic honey")) is None


def test_claim_is_not_laundered_through_a_substring_in_the_quote():
    # The quote contains "comparison" (which contains "iso") but never says ISO -> still flagged.
    hit = _chk("ISO certified pipes", _ev("read our price comparison guide"))
    assert hit in ("iso", "certified")           # the claim is rejected, not laundered


def test_multiword_and_hyphenated_tokens_still_work():
    assert _chk("gluten-free bread", _ev("fresh gluten-free bread")) is None      # grounded
    assert _chk("gluten-free bread", _ev("fresh bread")) == "gluten-free"          # not grounded
    assert _chk("clinically proven serum", _ev("a nice serum")) == "clinically proven"
    assert _chk("fda approved device", _ev("fda approved device")) is None         # grounded
