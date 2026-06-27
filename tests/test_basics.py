"""Sanity tests. Run with: python -m pytest tests/

These exist so the modules that don't touch the network can be
validated without spinning up Playwright.
"""
from scraper.url_utils import (
    normalize_url, same_registrable_host, get_domain_slug, site_root_if_deep,
)
from scraper.classify.page_type import classify_url
from scraper.schemas import PageTier, PageType


def test_site_root_if_deep_anchors_deep_content_pages():
    # A deep content page -> return the site root so identity anchors to the homepage.
    assert site_root_if_deep(
        "https://iti.gov.eg/diplomaStructure/abc/tracks/xyz") == "https://iti.gov.eg/"
    assert site_root_if_deep("https://www.elkbabgi.com/menu") == "https://www.elkbabgi.com/"
    assert site_root_if_deep(
        "https://sofitel.accor.com/en/hotels/5307/R002.restaurant.html") == "https://sofitel.accor.com/"
    assert site_root_if_deep("https://buffaloburger.com/branches/all/home") == "https://buffaloburger.com/"
    assert site_root_if_deep("https://example.com/about") == "https://example.com/"


def test_site_root_if_deep_leaves_homepages_and_locale_homes_alone():
    # Bare root and LOCALE homepages ARE the homepage -> never re-anchor (None).
    for u in (
        "https://nti.sci.eg/", "https://example.com",
        "https://www.orange.eg/en", "https://www.adidas.com/us",
        "https://www.defacto.com.eg/en-eg", "https://web.vodafone.com.eg/en/home",
    ):
        assert site_root_if_deep(u) is None, u


def test_normalize_strips_fragment_and_utm():
    a = normalize_url("https://Example.com/About?utm_source=ig&utm_campaign=x#team")
    b = normalize_url("https://example.com/About")
    assert a == b
    assert "utm_" not in a
    assert "#" not in a


def test_normalize_adds_https():
    assert normalize_url("example.com").startswith("https://")


def test_normalize_sorts_query():
    a = normalize_url("https://example.com/?b=2&a=1")
    b = normalize_url("https://example.com/?a=1&b=2")
    assert a == b


def test_same_host_www():
    assert same_registrable_host("https://www.example.com/a", "https://example.com/b")
    assert not same_registrable_host("https://example.com", "https://other.com")


def test_same_host_etld1_subdomains():
    # MEASURED on Vodafone EG: apex/www redirects to a `web.` subdomain and the
    # nav lives on `web.`/`eshop.` — these must be treated as the same site.
    assert same_registrable_host(
        "https://web.vodafone.com.eg/en/home", "https://www.vodafone.com.eg/"
    )
    assert same_registrable_host(
        "https://eshop.vodafone.com.eg/x", "https://www.vodafone.com.eg/"
    )
    # WE / Telecom Egypt: my.te.eg is the same site as www.te.eg
    assert same_registrable_host("https://my.te.eg/x", "https://www.te.eg/")
    # Multi-label public suffix (.co.uk) handled correctly.
    assert same_registrable_host(
        "https://shop.example.co.uk/x", "https://www.example.co.uk/"
    )


def test_same_host_not_over_broad():
    # A different registrable domain on the same brand stays EXTERNAL.
    assert not same_registrable_host(
        "https://careers.vodafone.com/x", "https://www.vodafone.com.eg/"
    )
    # Different ccTLD of the same brand is a different site.
    assert not same_registrable_host(
        "https://vodafone.co.uk/x", "https://vodafone.com.eg/y"
    )
    # Sites that merely SHARE a public suffix must not merge.
    assert not same_registrable_host("https://a.blogspot.com/", "https://b.blogspot.com/")


def test_same_host_fallback_for_unresolvable_hosts():
    # Hosts with no public-suffix match (localhost / IP / intranet) fall back to
    # the legacy www-stripped equality — must not crash and must stay sensible.
    assert same_registrable_host("http://localhost:8000/a", "http://localhost:8000/b")
    assert not same_registrable_host("http://localhost/a", "http://127.0.0.1/b")


def test_domain_slug():
    assert get_domain_slug("https://www.example-shop.com") == "example-shop_com"


def test_classify_contact_en():
    pt, tier = classify_url("https://x.com/contact-us", "Contact Us")
    assert pt == PageType.CONTACT
    assert tier == PageTier.HIGH


def test_classify_contact_ar():
    pt, tier = classify_url("https://x.com/", "تواصل معنا")
    assert pt == PageType.CONTACT
    assert tier == PageTier.HIGH


def test_classify_legal_skip():
    pt, tier = classify_url("https://x.com/privacy-policy", "Privacy")
    assert pt == PageType.LEGAL
    assert tier == PageTier.SKIP


def test_classify_other_lowtier():
    pt, tier = classify_url("https://x.com/random-page", "")
    assert pt == PageType.OTHER
    assert tier == PageTier.LOW


def test_classify_services_anchor():
    pt, tier = classify_url("https://x.com/we-do", "Our Services")
    assert pt == PageType.SERVICES
    assert tier == PageTier.HIGH


def test_classify_news_index_low_not_skip():
    pt, tier = classify_url("https://nti.sci.eg/news.php", "News")
    assert pt == PageType.BLOG
    assert tier == PageTier.LOW


def test_classify_news_detail_skip_with_id():
    pt, tier = classify_url("https://nti.sci.eg/news_details.php?id=1072", "Read more")
    assert pt == PageType.BLOG
    assert tier == PageTier.SKIP


def test_classify_blog_post_slug_skip():
    pt, tier = classify_url("https://example.com/blog/how-to-choose", "How to choose")
    assert pt == PageType.BLOG
    assert tier == PageTier.SKIP


def test_classify_article_detail_ar_skip():
    pt, tier = classify_url("https://example.com/articles/skin-care-tips", "مقال جديد")
    assert pt == PageType.BLOG
    assert tier == PageTier.SKIP