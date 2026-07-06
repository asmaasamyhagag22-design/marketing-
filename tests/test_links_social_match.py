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


def test_share_and_intent_buttons_are_not_the_brands_account():
    # SHARE / intent buttons live on a social host but are NOT the brand's account — counting
    # them inflated "social links" absurdly (Azza Fahmy: 20 -> 5 real accounts). They must be None.
    for u in [
        "https://www.facebook.com/sharer.php?u=https://brand.eg/products/x",
        "https://twitter.com/intent/tweet?text=X&url=https://brand.eg/y",
        "https://pinterest.com/pin/create/button/?url=https://brand.eg/z&media=https://brand.eg/i.jpg",
        "https://www.linkedin.com/sharing/share-offsite/?url=https://brand.eg/a",
        "https://api.whatsapp.com/send?text=Look%20https://brand.eg/b",
    ]:
        assert _social_platform(u) is None, u
    # …but the brand's OWN accounts on the same hosts are kept.
    assert _social_platform("https://www.facebook.com/AzzaFahmy") == "facebook"
    assert _social_platform("https://twitter.com/azzafahmy") == "twitter"
    assert _social_platform("https://www.pinterest.com/azzafahmy/") == "pinterest"
