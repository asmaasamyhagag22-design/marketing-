"""Vision photo-curation for the reel (reel.image_select).

The model call itself needs network + a key, so these tests exercise the
deterministic guardrails: tracking-beacon exclusion and honest-degrade when no
key is present. The 'keep only real_photo' logic is covered by the live Digilians
run (partner logos + QR dropped, 4 real photos kept).
"""
from __future__ import annotations

from reel.image_select import select_brand_photos


def test_no_key_degrades_to_input(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    urls = ["https://x.com/a.jpg", "https://x.com/b.jpg", "https://x.com/c.jpg"]
    out = select_brand_photos(urls, business_name="X", max_keep=2)
    assert out == urls[:2]


def test_tracking_pixels_filtered_even_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    urls = [
        "https://www.facebook.com/tr?id=123&ev=PageView",   # FB pixel
        "https://x.com/real-photo.jpg",
        "https://www.google-analytics.com/collect?v=1",     # GA beacon
        "https://x.com/another.jpg",
    ]
    out = select_brand_photos(urls, business_name="X")
    assert "facebook.com/tr" not in " ".join(out)
    assert all("google-analytics" not in u for u in out)
    assert "https://x.com/real-photo.jpg" in out


def test_single_or_empty_input_passthrough(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert select_brand_photos([], business_name="X") == []
    assert select_brand_photos(["https://x.com/only.jpg"], business_name="X") == \
        ["https://x.com/only.jpg"]
