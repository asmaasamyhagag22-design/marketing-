"""Evidence Ledger — deterministic proof that the central grounding gate works.

These tests pin the gate's behaviour WITHOUT any live LLM: a hard claim that is in the
evidence resolves to a source; a fabricated one ("170 years") is rejected; pure
paraphrase passes; Arabic inflections match. This is the rock-solid floor under the
(necessarily live) measurement harness in grounding/measure_step1.py.
"""
from __future__ import annotations

from grounding import EvidenceLedger, extract_claims


def _ef(value, quote, url="https://brand.example/about", conf="high"):
    """Build a serialized EvidencedField dict (value + one verbatim evidence quote)."""
    return {
        "value": value,
        "evidence": [{"block_id": "b1", "page_url": url, "quote": quote, "extractor": "llm"}],
        "confidence": conf,
        "source_type": "extracted",
    }


def _profile():
    """A minimal serialized BusinessProfile dict with real, sourced evidence."""
    return {
        "name": _ef("Digilians", "Digilians"),
        "tagline": _ef("الرواد الرقميون", "الرواد الرقميون"),
        "description": _ef(
            "We train 5000 youth every year in AI and cybersecurity.",
            "train 5000 youth every year in AI and cybersecurity",
        ),
        "value_propositions": [
            _ef("Fully funded scholarship", "a fully funded scholarship for every trainee"),
        ],
        "offerings": [
            {"name": "Nanodegree", "short_description": None, "price_text": None,
             "confidence": "high",
             "evidence": [{"block_id": "b2", "page_url": "https://brand.example/programs",
                           "quote": "Nanodegree in data science", "extractor": "llm"}]},
        ],
        "trust_signals": [],
    }


# --- claim extraction -------------------------------------------------

def test_paraphrase_has_no_hard_claim():
    # A benign brand-voice line asserts nothing checkable.
    assert extract_claims("خدمات تقربك أكتر") == []
    assert extract_claims("Connecting you to what matters") == []


def test_number_and_superlative_are_extracted():
    kinds = {c.kind for c in extract_claims("The only academy — 170 years of trust")}
    assert "number" in kinds
    assert "only" in kinds


def test_small_count_is_not_a_hard_claim():
    # "3 tracks" is not a fabrication risk; only significant numbers are claims.
    assert all(c.kind != "number" for c in extract_claims("3 tracks to choose from"))


# --- resolution -------------------------------------------------------

def test_real_number_resolves_to_its_source():
    led = EvidenceLedger.from_profile(_profile())
    res = led.resolve_claim("Train 5000 experts every year")
    assert res is not None
    assert res.source_url == "https://brand.example/about"
    assert "5000" in res.matched_quote


def test_fabricated_number_is_rejected():
    # THE "170 years" bug: nothing in the evidence says 170 -> no source -> REJECT.
    led = EvidenceLedger.from_profile(_profile())
    assert led.resolve_claim("بخبرة 170 سنة") is None
    assert led.resolve_claim("Serving for 170 years") is None


def test_grounded_superlative_resolves_via_arabic_inflection():
    # Headline "روّاد التحول الرقمي" should resolve against the tagline "الرواد الرقميون"
    # (same 'first/pioneer' group, different inflection + clitic).
    led = EvidenceLedger.from_profile(_profile())
    assert led.resolve_claim("روّاد التحول الرقمي") is not None


def test_unsupported_superlative_is_rejected():
    led = EvidenceLedger.from_profile(_profile())
    # Nothing in evidence claims "the only" / "الوحيد".
    assert led.resolve_claim("The only academy in Egypt") is None


# --- audit (the gate engine + export) ---------------------------------

def test_audit_fields_counts_unsourced_and_passes_clean_copy():
    led = EvidenceLedger.from_profile(_profile())
    report = led.audit_fields({
        "headline": "الرواد الرقميون",                  # grounded (tagline)
        "subheadline": "Train 5000 experts every year",  # grounded (description)
        "cta": "اعرف أكتر",                              # paraphrase, no claim
    })
    assert report.passes
    assert report.total_unsourced == 0


def test_audit_flags_a_fabricated_claim():
    led = EvidenceLedger.from_profile(_profile())
    report = led.audit_fields({
        "headline": "أكبر أكاديمية منذ 1850",  # fabricated: 1850 + 'largest' unsourced
        "cta": "سجّل الآن",
    })
    assert not report.passes
    assert report.total_unsourced >= 1
    # The export trail names the offending field + that it is unsourced.
    exported = report.export()
    assert exported["passes"] is False
    head = next(f for f in exported["fields"] if f["field"] == "headline")
    assert head["grounded"] is False
    assert any(c["sourced"] is False for c in head["claims"])


def test_export_carries_source_url_for_grounded_claims():
    led = EvidenceLedger.from_profile(_profile())
    exported = led.audit_fields({"sub": "Train 5000 experts"}).export()
    claim = exported["fields"][0]["claims"][0]
    assert claim["sourced"] is True
    assert claim["source_url"] == "https://brand.example/about"


def test_resolution_prefers_same_language_evidence():
    # The number 32 lives in BOTH an Arabic and an English entry; an Arabic claim must cite
    # the ARABIC quote (so the proof visually matches), an English claim the English one.
    prof = {
        "name": _ef("X", "X", "https://b/"),
        "tagline": _ef("ندرّب حتى 32 عاما", "ندرّب حتى 32 عاما", "https://b/ar"),
        "description": _ef("we train youth up to 32 years old", "up to 32 years old", "https://b/en"),
    }
    led = EvidenceLedger.from_profile(prof)
    ar = led.resolve_claim("ندعمك حتى 32 عاما")
    assert ar is not None and ar.matched_lang == "ar" and "عاما" in ar.matched_quote
    en = led.resolve_claim("we support you up to 32 years")
    assert en is not None and en.matched_lang == "en" and "years" in en.matched_quote


def test_cross_language_match_is_labeled_when_unavoidable():
    # Only ENGLISH evidence carries the number; an Arabic claim still resolves (the value is
    # real) but the export LABELS the language mismatch so it's documented, not a surprise.
    prof = {"name": _ef("X", "X", "https://b/"),
            "description": _ef("we train youth up to 32 years old", "up to 32 years old", "https://b/en")}
    led = EvidenceLedger.from_profile(prof)
    claim = led.audit_fields({"sub": "ندعمك حتى 32 عاما"}).export()["fields"][0]["claims"][0]
    assert claim["sourced"] is True
    assert claim["copy_lang"] == "ar" and claim["matched_lang"] == "en"
    assert claim["lang_mismatch"] is True


def test_full_run_wrapper_is_unwrapped():
    # A consolidated result.json wraps the profile under 'profile'.
    led = EvidenceLedger.from_profile({"profile": _profile(), "competitors": []})
    assert led.resolve_claim("Train 5000 experts") is not None
