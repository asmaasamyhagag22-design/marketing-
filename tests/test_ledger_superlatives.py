"""Superlative / ranking coverage CANARY for the Evidence-Ledger claim matcher.

WHY THIS FILE EXISTS (root-not-symptom)
---------------------------------------
The matcher catches falsifiable claims via a closed LEXICON, not a morphological pattern
(a naive EN `\\w+est` over-matches honest/interest/forest…; a naive AR `الأ\\w+` over-matches
الأساس/الأسبوع/الأحداث — both unusable). The trade-off of a closed list is that a NEW
superlative phrasing can slip through uncaught. This canary is the guardrail: every entry
in `MUST_BE_CAUGHT` must extract a claim. When a new uncovered superlative is found in the
wild, ADD IT HERE — the test then fails loudly until `grounding/ledger.py`'s lexicon covers
it. So the next hole is caught in CI, not at an agency.

`MUST_NOT_BE_CAUGHT` pins the Arabic precision the lexicon buys: superlative-SHAPED words
that are NOT elatives (الأساس=foundation, الأحداث=events, راقية=base adjective) must stay
pure paraphrase.
"""
from __future__ import annotations

import pytest

from grounding import EvidenceLedger, extract_claims


# Each must extract at least one hard claim. Grow this list when a new superlative appears.
MUST_BE_CAUGHT = [
    # EN -est superlatives
    "the fastest delivery", "the quickest setup", "the easiest way to pay",
    "the simplest plan", "the smartest choice", "the strongest signal",
    "the safest option", "the healthiest meals", "the freshest produce",
    "the cheapest rates", "the highest quality", "the lowest price",
    "the widest coverage", "the longest battery", "the cleanest energy",
    "the purest water",
    # EN ranking / already-covered superiority words (regression anchors)
    "#1 in the market", "no.1 provider", "the best in class", "the leading academy",
    "the largest network", "the only clinic", "world class service", "award winning team",
    # AR elatives (أفعل التفضيل)
    "الأسرع في السوق", "الأسهل استخدامًا", "الأرخص سعرًا", "الأذكى في فئته",
    "الأحدث تقنيًا", "الأأمن لبياناتك", "الأنظف بيئيًا", "الأنقى مكوناتٍ",
    "الأجود خامة", "الأطول عمرًا", "الأوسع انتشارًا", "الأعلى جودة", "الأدنى سعرًا",
    # AR already-covered superiority / ranking
    "الأفضل في مجاله", "الأكبر في الشرق الأوسط", "الوحيد المعتمد", "رواد التحول",
    "حاصل على جائزة", "خصم 50%", "خبرة 30 سنة",
]

# Superlative-SHAPED but NOT a claim — must stay pure paraphrase (zero false positive).
MUST_NOT_BE_CAUGHT = [
    "نبني على الأساس الصحيح",     # الأساس = foundation (not the elative 'أساس')
    "تابع آخر الأحداث معنا",       # الأحداث = events (not 'أحدث' = newest)
    "تجربة راقية تستحقها",         # راقية = base adjective (not the elative 'أرقى')
    "نراجع الأسعار شهريًا",        # الأسعار = prices
    "ننظّم الأعمال بكفاءة",         # الأعمال = works/business
    "نتابع الأخبار باستمرار",       # الأخبار = news
    "the honest truth about us",  # 'honest' is not a superlative
    "we value your interest",     # 'interest' is not a superlative
    "a modest family business",   # 'modest' is not a superlative
]


@pytest.mark.parametrize("text", MUST_BE_CAUGHT)
def test_superlative_is_caught(text):
    kinds = [c.kind for c in extract_claims(text)]
    assert kinds, f"UNCOVERED superlative/ranking slipped the matcher: {text!r}"


@pytest.mark.parametrize("text", MUST_NOT_BE_CAUGHT)
def test_superlative_shaped_paraphrase_is_not_caught(text):
    kinds = [c.kind for c in extract_claims(text)]
    # No ranking/superiority claim should be raised for benign superlative-shaped words.
    assert not ({"superlative", "first", "best", "largest", "only"} & set(kinds)), \
        f"FALSE POSITIVE on benign text {text!r}: {kinds}"


def test_unsourced_superlative_is_dropped_but_grounded_one_resolves():
    # A 'fastest' claim with NO superlative in evidence -> REJECT; with evidence -> resolve.
    def _ef(v):
        return {"value": v, "evidence": [{"page_url": "https://b/p", "quote": v}],
                "confidence": "high"}
    no_super = EvidenceLedger.from_profile({"name": _ef("Acme"),
                                            "description": _ef("we deliver parcels")})
    has_super = EvidenceLedger.from_profile({"name": _ef("Acme"),
                                             "tagline": _ef("الأسرع في توصيل الطرود")})
    assert no_super.resolve_claim("الأسرع في السوق") is None        # fabricated -> dropped
    assert has_super.resolve_claim("الأسرع في السوق") is not None    # grounded -> resolved


def test_hash_one_ranking_resolves_only_against_a_leadership_claim():
    # '#1' maps to the 'first' group: a brand that claims leadership grounds it (paraphrase);
    # a brand that makes no such claim does NOT -> the fabricated '#1' is dropped.
    def _ef(v):
        return {"value": v, "evidence": [{"page_url": "https://b/p", "quote": v}],
                "confidence": "high"}
    assert "first" in {c.kind for c in extract_claims("The #1 academy")}
    leader = EvidenceLedger.from_profile({"name": _ef("Acme"),
                                          "tagline": _ef("the leading coding academy")})
    plain = EvidenceLedger.from_profile({"name": _ef("Acme"),
                                         "description": _ef("a coding academy in Cairo")})
    assert leader.resolve_claim("The #1 academy") is not None        # grounded paraphrase
    assert plain.resolve_claim("The #1 academy") is None             # fabricated -> dropped
