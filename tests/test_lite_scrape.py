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
