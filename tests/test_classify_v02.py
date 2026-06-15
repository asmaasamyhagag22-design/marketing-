"""Classifier and crawler regression tests for patch v0.2-a.

Covers the new page types added for universal business coverage:
- Restaurant/cafe: DELIVERY_ORDER, CATERING, expanded MENU patterns
- Education: COURSES, PROGRAMS, ADMISSIONS
- Multi-location: BRANCHES_LOCATIONS
- Ecommerce: expanded PRODUCTS (collections, best-sellers)
- Social proof: PORTFOLIO, TESTIMONIALS, EVENTS, OFFERS
- Peripheral: GALLERY

Each new pattern is tested in both English and Arabic where applicable.
The tail of the file also re-asserts that existing patterns still work
(regression guard for the rewritten PAGE_TYPE_PATTERNS list).
"""
from scraper.classify.page_type import classify_url
from scraper.schemas import PageTier, PageType


# ---------------------------------------------------------------------
# Restaurant / cafe
# ---------------------------------------------------------------------

def test_classify_our_menu():
    pt, tier = classify_url("https://x.com/our-menu", "Our Menu")
    assert pt == PageType.MENU
    assert tier == PageTier.HIGH


def test_classify_food_menu():
    pt, tier = classify_url("https://x.com/food-menu/", "Food Menu")
    assert pt == PageType.MENU
    assert tier == PageTier.HIGH


def test_classify_dishes_url():
    pt, tier = classify_url("https://x.com/dishes", "")
    assert pt == PageType.MENU
    assert tier == PageTier.HIGH


def test_classify_menu_ar():
    pt, tier = classify_url("https://x.com/قائمة-الطعام", "قائمتنا")
    assert pt == PageType.MENU
    assert tier == PageTier.HIGH


def test_classify_order_online():
    pt, tier = classify_url("https://x.com/order-online", "Order Online")
    assert pt == PageType.DELIVERY_ORDER
    assert tier == PageTier.HIGH


def test_classify_delivery_ar():
    pt, tier = classify_url("https://x.com/توصيل", "اطلب الآن")
    assert pt == PageType.DELIVERY_ORDER
    assert tier == PageTier.HIGH


def test_classify_catering_en():
    pt, tier = classify_url("https://x.com/catering-services", "Catering")
    assert pt == PageType.CATERING
    assert tier == PageTier.HIGH


# ---------------------------------------------------------------------
# Multi-location
# ---------------------------------------------------------------------

def test_classify_branches_en():
    pt, tier = classify_url("https://x.com/branches", "Our Branches")
    assert pt == PageType.BRANCHES_LOCATIONS
    assert tier == PageTier.HIGH


def test_classify_branches_ar():
    pt, tier = classify_url("https://x.com/فروعنا", "فروعنا")
    assert pt == PageType.BRANCHES_LOCATIONS
    assert tier == PageTier.HIGH


def test_classify_store_locator():
    pt, tier = classify_url("https://x.com/store-locator", "Find a Store")
    assert pt == PageType.BRANCHES_LOCATIONS
    assert tier == PageTier.HIGH


# ---------------------------------------------------------------------
# Education / training
# ---------------------------------------------------------------------

def test_classify_courses_en():
    pt, tier = classify_url("https://x.com/courses", "Our Courses")
    assert pt == PageType.COURSES
    assert tier == PageTier.HIGH


def test_classify_courses_ar():
    pt, tier = classify_url("https://x.com/كورسات", "الدورات")
    assert pt == PageType.COURSES
    assert tier == PageTier.HIGH


def test_classify_programs_en():
    pt, tier = classify_url("https://x.com/academic-programs", "Programs")
    assert pt == PageType.PROGRAMS
    assert tier == PageTier.HIGH


def test_classify_training_anchor_ar():
    pt, tier = classify_url("https://x.com/something", "تدريب")
    assert pt == PageType.PROGRAMS
    assert tier == PageTier.HIGH


def test_classify_admissions_en():
    pt, tier = classify_url("https://x.com/admissions", "Apply Now")
    assert pt == PageType.ADMISSIONS
    assert tier == PageTier.HIGH


def test_classify_admissions_ar():
    pt, tier = classify_url("https://x.com/التقديم", "قدم الآن")
    assert pt == PageType.ADMISSIONS
    assert tier == PageTier.HIGH


# ---------------------------------------------------------------------
# Ecommerce additions
# ---------------------------------------------------------------------

def test_classify_collections():
    pt, tier = classify_url("https://x.com/collections", "Our Collections")
    assert pt == PageType.PRODUCTS
    assert tier == PageTier.HIGH


def test_classify_best_sellers():
    pt, tier = classify_url("https://x.com/best-sellers", "Best Sellers")
    assert pt == PageType.PRODUCTS
    assert tier == PageTier.HIGH


def test_classify_new_arrivals():
    pt, tier = classify_url("https://x.com/new-arrivals", "New")
    assert pt == PageType.PRODUCTS
    assert tier == PageTier.HIGH


# ---------------------------------------------------------------------
# Social proof / narrative
# ---------------------------------------------------------------------

def test_classify_portfolio_en():
    pt, tier = classify_url("https://x.com/portfolio", "Our Work")
    assert pt == PageType.PORTFOLIO
    assert tier == PageTier.MEDIUM


def test_classify_case_studies():
    pt, tier = classify_url("https://x.com/case-studies", "Case Studies")
    assert pt == PageType.PORTFOLIO
    assert tier == PageTier.MEDIUM


def test_classify_portfolio_ar():
    pt, tier = classify_url("https://x.com/أعمالنا", "أعمالنا")
    assert pt == PageType.PORTFOLIO
    assert tier == PageTier.MEDIUM


def test_classify_testimonials_en():
    pt, tier = classify_url("https://x.com/testimonials", "Reviews")
    assert pt == PageType.TESTIMONIALS
    assert tier == PageTier.MEDIUM


def test_classify_testimonials_ar():
    pt, tier = classify_url("https://x.com/شهادات", "آراء العملاء")
    assert pt == PageType.TESTIMONIALS
    assert tier == PageTier.MEDIUM


def test_classify_events_en():
    pt, tier = classify_url("https://x.com/upcoming-events", "Events")
    assert pt == PageType.EVENTS
    assert tier == PageTier.MEDIUM


def test_classify_offers_en():
    pt, tier = classify_url("https://x.com/special-offers", "Offers")
    assert pt == PageType.OFFERS
    assert tier == PageTier.MEDIUM


def test_classify_offers_ar():
    pt, tier = classify_url("https://x.com/عروض", "عروضنا")
    assert pt == PageType.OFFERS
    assert tier == PageTier.MEDIUM


# ---------------------------------------------------------------------
# Peripheral
# ---------------------------------------------------------------------

def test_classify_gallery_en():
    pt, tier = classify_url("https://x.com/gallery", "Photo Gallery")
    assert pt == PageType.GALLERY
    assert tier == PageTier.LOW


def test_classify_gallery_ar():
    pt, tier = classify_url("https://x.com/المعرض", "صور")
    assert pt == PageType.GALLERY
    assert tier == PageTier.LOW


# ---------------------------------------------------------------------
# Legal/policy precedence (terms-of-service must not steal a SERVICES slot)
# ---------------------------------------------------------------------

def test_legal_pages_skip_and_dont_steal_services_slot():
    """A legal/policy URL must classify LEGAL/SKIP even when it contains 'service'
    (terms-of-service) or 'pricing' (pricing-policy) — MEASURED: 9/63 legal URLs
    across 7 saved sites were wrongly tiered HIGH/MEDIUM and stole crawl slots."""
    for url, anchor in [
        ("https://eg.azzafahmy.com/policies/terms-of-service", "Terms & Conditions"),
        ("https://www.brilliantearth.com/customer-service-policies/", "Policies"),
        ("https://www.glamira.com/pricing-policy/", "Pricing Policy"),
        ("https://x.com/privacy-policy", "Privacy"),
        ("https://x.com/refund-policy", "Refunds"),
        ("https://x.com/cookie-policy", "Cookies"),
    ]:
        pt, tier = classify_url(url, anchor)
        assert pt == PageType.LEGAL and tier == PageTier.SKIP, f"{url} -> {pt}/{tier}"


def test_legal_check_does_not_break_real_pages():
    """Real content pages must be unchanged (no false legal match)."""
    assert classify_url("https://x.com/services", "Services")[0] == PageType.SERVICES
    assert classify_url("https://x.com/our-services", "")[0] == PageType.SERVICES
    assert classify_url("https://x.com/pricing", "")[0] == PageType.PRICING
    assert classify_url("https://x.com/collections/all", "Catalog")[0] == PageType.PRODUCTS


# ---------------------------------------------------------------------
# Regression: existing patterns must keep working after the rewrite
# ---------------------------------------------------------------------

def test_regression_classify_contact():
    pt, tier = classify_url("https://x.com/contact-us", "Contact")
    assert pt == PageType.CONTACT
    assert tier == PageTier.HIGH


def test_regression_classify_services():
    pt, tier = classify_url("https://x.com/services", "Our Services")
    assert pt == PageType.SERVICES
    assert tier == PageTier.HIGH


def test_regression_classify_about():
    pt, tier = classify_url("https://x.com/about-us", "About Us")
    assert pt == PageType.ABOUT
    assert tier == PageTier.MEDIUM


def test_regression_classify_pricing():
    pt, tier = classify_url("https://x.com/pricing", "Pricing")
    assert pt == PageType.PRICING
    assert tier == PageTier.HIGH


def test_regression_classify_blog_low():
    pt, tier = classify_url("https://x.com/blog", "Blog")
    assert pt == PageType.BLOG
    assert tier == PageTier.LOW


def test_regression_classify_legal_skip():
    pt, tier = classify_url("https://x.com/privacy-policy", "Privacy")
    assert pt == PageType.LEGAL
    assert tier == PageTier.SKIP


# ---------------------------------------------------------------------
# Crawler tier priority — confirm new types slot into the priority dict
# without raising KeyError. (The actual ordering is tested indirectly via
# crawler integration tests, but this guards the dict's completeness.)
# ---------------------------------------------------------------------

def test_crawler_type_priority_covers_all_page_types():
    """Every PageType value (except FAQ-style internals) must have a slot
    in the crawler's type_priority dict, so candidates don't fall through
    to the default '50' sort key in unexpected ways."""
    # We import lazily to avoid pulling Playwright at module load time
    import sys
    import types as _types

    # Stub playwright before importing crawler (same pattern as other tests)
    _fake = _types.ModuleType("playwright")
    _fake_sync = _types.ModuleType("playwright.sync_api")
    class _Stub:
        ...
    for n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
        setattr(_fake_sync, n, _Stub)
    _fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
    _fake_sync.Error = type("Error", (Exception,), {})
    sys.modules.setdefault("playwright", _fake)
    sys.modules.setdefault("playwright.sync_api", _fake_sync)

    import inspect

    from scraper import crawler as crawler_mod

    # Pull the type_priority dict out of _select_subpages_to_fetch's source
    src = inspect.getsource(crawler_mod._select_subpages_to_fetch)
    # Sanity: every new page type appears in the source as PageType.NAME
    for member in PageType:
        # OTHER and the existing ones must appear in the priority table.
        # We check the lowercase enum value is referenced in the source.
        token = f"PageType.{member.name}"
        assert token in src, (
            f"crawler.type_priority is missing {token} — sort fallback "
            f"would push it to '50' (OTHER) tier."
        )


def test_evidence_pack_scores_all_page_types():
    """Every PageType must have a slot in _PAGE_TYPE_SCORE so the pack
    builder isn't quietly scoring new types as 0."""
    from business_profile.llm.evidence_pack import _PAGE_TYPE_SCORE

    for member in PageType:
        assert member.value in _PAGE_TYPE_SCORE, (
            f"_PAGE_TYPE_SCORE missing entry for PageType.{member.name} "
            f"('{member.value}') — new offering pages would score 0."
        )
