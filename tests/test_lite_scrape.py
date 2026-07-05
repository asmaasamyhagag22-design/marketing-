"""lite_peer_dims — light peer dimensions for the sync web SWOT path (hermetic)."""
from __future__ import annotations

from competitor.lite_scrape import lite_peer_dims

_HTML = (
    '<a href="https://facebook.com/peer">Facebook</a>'
    '<a href="https://instagram.com/peer">Instagram</a>'
    '<a href="https://facebook.com/peer">Facebook</a>'          # dup social -> 1
    '<a href="/contact/">Contact</a>'
    '<a href="/contact/">Book a Meeting</a>'                     # booking CTA
    '<a href="/shop">Shop now</a>'                               # CTA
    '<a href="https://wa.me/20100000000">WhatsApp</a>'
    '<a href="/about">About</a>'
)


def test_dims_from_real_anchor_inventory(monkeypatch):
    # The SSRF guard resolves DNS; a fake test domain would fail it. Bypass the
    # guard here (its rejection behavior is pinned by the test below).
    import scraper.url_utils as uu
    monkeypatch.setattr(uu, "is_safe_public_url", lambda u: True)
    dims = lite_peer_dims("https://peer.example/", fetch=lambda u: _HTML)
    assert dims is not None
    assert dims["social_count"] == 3          # fb + ig + wa.me (a social platform), dup collapsed
    assert dims["cta_count"] == 2             # Book a Meeting + Shop now
    assert dims["whatsapp"] is True
    assert dims["online_booking"] is True
    # Un-detectable dims stay UNKNOWN — never inferred (rule 4).
    assert dims["offerings_count"] is None
    assert dims["trust_count"] is None
    assert dims["bilingual"] is None
    assert dims["shows_reviews"] is None


def test_ssrf_guarded_and_failures_yield_none_never_raise(monkeypatch):
    # SSRF: loopback/metadata targets are rejected by the real guard (no DNS needed).
    assert lite_peer_dims("http://127.0.0.1/admin", fetch=lambda u: _HTML) is None
    assert lite_peer_dims("http://169.254.169.254/meta", fetch=lambda u: _HTML) is None
    assert lite_peer_dims("", fetch=lambda u: _HTML) is None

    # Fetch failures (guard bypassed so the failure path itself is exercised).
    import scraper.url_utils as uu
    monkeypatch.setattr(uu, "is_safe_public_url", lambda u: True)

    def boom(u):
        raise RuntimeError("network down")
    assert lite_peer_dims("https://peer.example/", fetch=boom) is None
    assert lite_peer_dims("https://peer.example/", fetch=lambda u: "") is None


def test_js_shell_with_no_anchors_is_unknown_not_false_zeros(monkeypatch):
    # A client-rendered (JS-only) shell serves NO anchors — its social/CTA/WhatsApp load via
    # JS. Reporting "0 social / no WhatsApp" would be evidence-of-ABSENCE as knowledge; the
    # whole peer must stay UNKNOWN (None), like a fetch failure (rule 4).
    import scraper.url_utils as uu
    monkeypatch.setattr(uu, "is_safe_public_url", lambda u: True)
    shell = '<html><head><title>App</title></head><body><div id="root"></div></body></html>'
    assert lite_peer_dims("https://spa.example/", fetch=lambda u: shell) is None


def test_real_page_without_social_still_reports_honest_zeros(monkeypatch):
    # A REAL page (has anchors) with no social/CTA legitimately reports 0 — that is a genuine
    # observation, not an unknown, so the feature is preserved.
    import scraper.url_utils as uu
    monkeypatch.setattr(uu, "is_safe_public_url", lambda u: True)
    html = '<a href="/about">About</a><a href="/team">Team</a><a href="/faq">FAQ</a>'
    dims = lite_peer_dims("https://plain.example/", fetch=lambda u: html)
    assert dims is not None
    assert dims["social_count"] == 0 and dims["cta_count"] == 0
    assert dims["whatsapp"] is False and dims["online_booking"] is False
