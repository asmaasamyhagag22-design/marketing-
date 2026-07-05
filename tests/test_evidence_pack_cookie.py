# -*- coding: utf-8 -*-
"""Evidence-pack boilerplate filter must not delete the food 'cookie' (2026-07-05 audit).

A bare `\\bcookie` pattern treated every "cookie" as a consent banner, silently dropping REAL
dessert menu blocks from the evidence pack — MEASURED 186 blocks across 8 corpus sites, incl.
buffaloburger "Cookie Dough" / "SPOON ME COOKIE" (EGP 100) and mcdonalds "Chocolate Chip
Cookie". Now only cookie-CONSENT phrasing is boilerplate; the food is kept as evidence
(offerings + grounding).

Hermetic: pure predicate, no I/O.
"""
from business_profile.llm.evidence_pack import _is_boilerplate


def test_food_cookies_are_kept():
    for t in ("Cookie Dough With Chocolate", "SPOON ME COOKIE", "Chocolate Chip Cookie",
              "Double Chocolate Chip Cookie", "MATCHA PISTACHE Cookie Dough With Pistachio",
              "Cookies and Cream Milkshake", "A dozen fresh cookies", "Oatmeal Cookie EGP 25"):
        assert not _is_boilerplate(t), t


def test_cookie_consent_banners_are_dropped():
    for t in ("Accept All Cookies", "Reject All Cookies",
              "Accept All Cookies Manage Preferences", "Cookie Use",
              "Cookies and Personal Data", "We use cookies to improve your experience",
              "This site uses cookies", "Cookie Policy", "Manage cookie settings",
              "About cookies on this site"):
        assert _is_boilerplate(t), t


def test_other_boilerplate_still_dropped():
    assert _is_boilerplate("© 2026 Buffalo Burger. All rights reserved.")
    assert _is_boilerplate("Privacy Policy")
    assert _is_boilerplate("GDPR compliance")
