"""Sanity tests. Run with: python -m pytest tests/

These exist so the modules that don't touch the network can be
validated without spinning up Playwright.
"""
from scraper.url_utils import normalize_url, same_registrable_host, get_domain_slug
from scraper.classify.page_type import classify_url
from scraper.schemas import PageTier, PageType


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