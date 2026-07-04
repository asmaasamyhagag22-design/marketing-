"""The nahdionline.com failure chain (owner: "الاسكرابر بخراب") — hermetic regressions.

Measured on the real scrape: (1) 432 'Shop by brands' promo tiles classified as
primary_brand_logo — the CDN host `dam.nahdionline.com` gave every asset a
brand_name_match and the carousel path matched the 'brand' logo-keyword; (2) 10+ dead
sitemap files serially ate the crawl budget -> budget_exceeded after ZERO subpages of
a 300-link store -> no product pages -> "no prices"; (3) /plp/ /pdp/ product URLs
weren't recognized -> the e-commerce budget never triggered.
"""
from __future__ import annotations

from scraper.classify.page_type import classify_url
from scraper.extractors.visual import _score_logo_candidates


def _cand(src, *, in_header=False, in_footer=False, alt="", ctx=""):
    return {
        "src": src, "alt": alt, "context_text": ctx, "class_id": "", "href": "",
        "source_type": "img", "in_header": in_header, "near_nav": in_header,
        "in_footer": in_footer, "links_to_home": in_header,
        "width": None, "height": None, "is_social": False, "is_hero_gallery": False,
    }


def test_cdn_host_and_brand_carousel_do_not_outrank_the_real_logo():
    computed = {"site_name": "Nahdi"}
    page = "https://www.nahdionline.com/ar-sa"
    tiles = [
        _cand("https://dam.nahdionline.com/m/1/original/06_HP_Shop_by_brands_CeraVe-588x960.jpg"),
        _cand("https://dam.nahdionline.com/m/2/original/06_HP_Shop_by_brands_Meridol.jpg"),
    ]
    real = _cand("https://dam.nahdionline.com/m/9/original/nahdi-logo-footer.png",
                 in_header=True, alt="Nahdi")
    scored = _score_logo_candidates(tiles + [real], computed, page)
    by_src = {c.src: c for c in scored}

    real_c = by_src[real["src"]]
    assert real_c.score > max(by_src[t["src"]].score for t in tiles) + 20
    for t in tiles:
        c = by_src[t["src"]]
        # The CDN host must not grant a brand match, and the multi-brand shop
        # carousel is hard-demoted — a promo tile can never be the primary logo.
        assert "brand_name_match" not in c.reasons
        assert "penalty_brand_listing_section" in c.reasons
        assert c.classification != "primary_brand_logo"


def test_footer_only_brand_logo_is_rescued_but_generic_badges_are_not():
    """nahdi carries its mark ONLY in the footer (the header logo is an uncaptured
    inline asset) — after the tile fix the primary came back None while the real
    `nahdi-logo-footer.png` topped the list as footer_logo. The rescue promotes it;
    a generic VAT badge (also footer, also 'logo' in filename) stays out via the
    score floor + the brand+logo signature pair."""
    from scraper.extractors.visual import _choose_primary_logo
    from scraper.schemas import LogoCandidate

    real = LogoCandidate(
        src="https://dam.x.com/nahdi-logo-footer.png", page_url="https://x.com/", source_type="img",
        classification="footer_logo", confidence=0.5, score=52.0,
        reasons=["logo_keyword", "brand_name_match", "img", "suitable_logo_shape",
                 "footer_only"])
    vat = LogoCandidate(
        src="https://dam.x.com/vat-logo-1.png", page_url="https://x.com/", source_type="img",
        classification="footer_logo", confidence=0.4, score=40.0,
        reasons=["logo_keyword", "brand_name_match", "img", "footer_only"])
    chosen = _choose_primary_logo([vat, real], ["nahdi"])
    assert chosen is not None and "nahdi-logo-footer" in chosen.src
    assert chosen.classification == "primary_brand_logo"
    # A footer with ONLY generic badges (below the floor) stays None — honest.
    assert _choose_primary_logo([vat], ["nahdi"]) is None


def test_dead_sitemap_host_trips_the_breaker_not_the_budget(monkeypatch):
    import scraper.sitemap as sm

    fetched = []
    monkeypatch.setattr(sm, "_fetch_sitemap_bytes",
                        lambda url: fetched.append(url) or None)   # every fetch dead

    class _Robots:
        # Same eTLD+1 as the site (a subdomain host, like sitemap.nahdionline.com).
        sitemap_urls = [f"https://sitemap.nahdi-test.com/s{i}.xml" for i in range(10)]

    res = sm.discover_sitemap_urls("https://www.nahdi-test.com/", _Robots())
    assert len(fetched) == 2, "2 consecutive dead fetches must open the breaker"
    assert any("breaker_open" in n for n in res.notes)
    assert res.urls == []


def test_plp_pdp_classify_as_products():
    from scraper.schemas import PageTier, PageType
    for url in ("https://www.nahdionline.com/ar-sa/plp/flash-sales",
                "https://www.nahdionline.com/ar-sa/pdp/panadol-extra"):
        pt, tier = classify_url(url)
        assert pt == PageType.PRODUCTS and tier == PageTier.HIGH


def test_min_subpage_attempts_config_exists():
    from scraper.config import MIN_SUBPAGE_ATTEMPTS
    assert MIN_SUBPAGE_ATTEMPTS >= 3
