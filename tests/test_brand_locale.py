"""Evidence-derived brand locale (poster/locale.py) — FIX-C3/D of the 2026-07-11 campaign.

The primer must come from PROFILE EVIDENCE (ccTLD -> service_areas -> phone e164 -> language),
be universal (any country, nothing hardcoded), and stay HONEST: unknown locale injects no
cultural claim. Hermetic.
"""
from __future__ import annotations

from poster.locale import brand_locale, country_of


def test_cctld_wins():
    assert country_of({"source_url": "https://nti.sci.eg/"}) == "Egypt"
    assert country_of({"source_url": "https://brand.com.sa/"}) == "Saudi Arabia"
    assert country_of({"source_url": "https://shop.co.uk/"}) == "the UK"


def test_service_areas_fallback_for_dot_com():
    p = {"source_url": "https://brand.com/",
         "service_areas": [{"value": "Cairo, Egypt"}]}
    assert country_of(p) == "Egypt"


def test_phone_e164_fallback():
    p = {"source_url": "https://brand.com/",
         "contact_channels": {"phones": [{"e164": "+201099569334", "raw": "010..."}]}}
    assert country_of(p) == "Egypt"
    p2 = {"contact_channels": {"phones": [{"e164": "+966501234567"}]}}
    assert country_of(p2) == "Saudi Arabia"


def test_primer_wording_and_language_cue():
    country, line = brand_locale({"source_url": "https://x.eg/"})
    assert country == "Egypt"
    assert "authentically from Egypt" in line and "everyday style" in line
    assert "Khaleeji" in line                        # anti-drift kept from the proven wording
    # Arabic content, no country evidence -> honest REGIONAL cue only
    c2, line2 = brand_locale({"source_url": "https://brand.com/", "languages": ["ar"]})
    assert c2 == "" and "Arabic-speaking-region" in line2


def test_unknown_locale_injects_nothing():
    assert brand_locale({"source_url": "https://brand.com/"}) == ("", "")
    assert brand_locale({}) == ("", "")


def test_arabic_saudi_brand_is_not_forced_egyptian():
    # the anti-hardcode regression: an ARABIC brand with .sa evidence must be Saudi, never
    # 'Egyptian by default' (the reel used to map ANY Arabic brand to Egypt)
    country, line = brand_locale({"source_url": "https://brand.sa/", "languages": ["ar"]})
    assert country == "Saudi Arabia" and "Saudi Arabia" in line and "Egypt" not in line
