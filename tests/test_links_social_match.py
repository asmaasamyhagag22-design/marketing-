"""H4 gate: social-platform classification matches a host EXACTLY or as a subdomain —
never as a substring.

Regression origin (2026-07-05 audit): the matcher used `dom in host`, so any host
CONTAINING a short social domain was misclassified — `x.com` is a substring of
xerox.com / box.com / netflix.com / fedex.com (all -> "twitter"), and `t.me` of
content.medium.com (-> "telegram"). That mislabels external links and, when the subject's
OWN host contains such a substring, drops its internal links from the crawl frontier
(internal/CTA links only enter the frontier — a link tagged SOCIAL never does).

Hermetic: pure function, no network.
"""
from scraper.extractors.links import _social_platform


def test_substring_hosts_are_not_social():
    for host in ["xerox.com", "box.com", "netflix.com", "fedex.com", "content.medium.com",
                 "essex.com", "phoenix.com"]:
        assert _social_platform(f"https://{host}/page") is None, host


def test_exact_and_subdomain_hosts_are_social():
    assert _social_platform("https://facebook.com/brand") == "facebook"
    assert _social_platform("https://www.facebook.com/brand") == "facebook"
    assert _social_platform("https://l.facebook.com/l.php?u=x") == "facebook"
    assert _social_platform("https://m.youtube.com/@brand") == "youtube"
    assert _social_platform("https://x.com/brand") == "twitter"
    assert _social_platform("https://t.me/brand") == "telegram"
    assert _social_platform("https://wa.me/201234") == "whatsapp"


def test_non_social_host_is_none():
    assert _social_platform("https://example.com/") is None
    assert _social_platform("https://shop.mybrand.eg/products") is None
