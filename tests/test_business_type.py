"""BusinessTypeClassifier: LOCAL / ECOMMERCE / HYBRID / UNKNOWN.

Pure, grounded classification driven by physical address + category + ecommerce
structural signals (priced offerings, cart/checkout/product paths). Every result
exposes the signals that drove it.
"""
from __future__ import annotations

from types import SimpleNamespace as NS

from competitor.business_type import classify_business_type, BusinessType


def _profile(category=None, locations=None, offerings=None):
    # mimic EvidencedField[category] with a .value, like the real profile
    cat = NS(value=category) if category is not None else None
    return NS(category=cat, locations=locations or [], offerings=offerings or [])


def test_ecommerce_no_address():
    # thehairaddict.net shape: category ecommerce, no physical address
    r = classify_business_type(_profile(category="ecommerce"))
    assert r.business_type is BusinessType.ECOMMERCE
    assert r.signals["has_physical_address"] is False


def test_local_with_address():
    loc = NS(address_text="Road 9, Maadi, Cairo", latitude=None, longitude=None)
    r = classify_business_type(_profile(category="clinic", locations=[loc]))
    assert r.business_type is BusinessType.LOCAL


def test_hybrid_retail_with_address_and_cart():
    loc = NS(address_text="Mall of Egypt", latitude=29.9, longitude=31.0)
    off = [NS(price_text="EGP 100", page_url="https://x.com/product/abc")]
    man = NS(links=NS(cta_candidates=[NS(href="https://x.com/cart")],
                      internal=[], external=[]))
    r = classify_business_type(_profile(category="retail", locations=[loc], offerings=off), man)
    assert r.business_type is BusinessType.HYBRID
    assert r.signals["cart_or_checkout_links"] is True


def test_unknown_when_no_signals():
    r = classify_business_type(_profile(category="other"))
    assert r.business_type is BusinessType.UNKNOWN


def test_ecommerce_from_structural_signals_only():
    # ambiguous category but clear store structure -> ecommerce
    off = [NS(price_text="EGP 50", page_url="https://x.com/products/a"),
           NS(price_text="EGP 80", page_url="https://x.com/products/b")]
    r = classify_business_type(_profile(category="other", offerings=off))
    assert r.business_type is BusinessType.ECOMMERCE
    assert r.signals["priced_offerings"] == 2


def test_tolerates_dict_profile():
    r = classify_business_type({"category": {"value": "ecommerce"}, "locations": [], "offerings": []})
    assert r.business_type is BusinessType.ECOMMERCE


def test_reach_category_without_address_is_web_only_not_local():
    # ITI shape: an IT-training institute (education), no scraped address. It competes by
    # CATEGORY (other institutes/bootcamps/platforms), not proximity -> REACH (web discovery),
    # NOT LOCAL (which gave it universities + its own branch via Places).
    for cat in ("education", "professional_services", "services_b2b", "agency"):
        r = classify_business_type(_profile(category=cat))
        assert r.business_type is BusinessType.REACH, cat
        assert r.signals["reach_category"] is True


def test_reach_category_with_a_local_footprint_is_hybrid():
    # A training institute WITH a real campus address still has category peers, so it gets BOTH
    # engines (Places local peers + web category peers), never pure proximity-LOCAL.
    loc = NS(address_text="Smart Village, Giza", latitude=None, longitude=None)
    r = classify_business_type(_profile(category="education", locations=[loc]))
    assert r.business_type is BusinessType.HYBRID
    assert r.signals["reach_category"] is True and r.signals["has_physical_address"] is True


def test_reach_category_beats_priced_offering_ecom_signal():
    # ITI's real profile has 2 priced COURSES -> ecom_structural=True. A reach category must NOT be
    # mislabelled ECOMMERCE by that weak signal; it still routes to web discovery as REACH.
    off = [NS(price_text="EGP 5000", page_url="https://iti.gov.eg/a"),
           NS(price_text="EGP 8000", page_url="https://iti.gov.eg/b")]
    r = classify_business_type(_profile(category="education", offerings=off))
    assert r.business_type is BusinessType.REACH
    assert r.signals["reach_category"] is True and r.signals["priced_offerings"] == 2


def test_proximity_local_categories_are_unchanged():
    # restaurant/clinic/etc. still compete locally -> LOCAL, not REACH.
    r = classify_business_type(_profile(category="restaurant"))
    assert r.business_type is BusinessType.LOCAL and r.signals["reach_category"] is False
