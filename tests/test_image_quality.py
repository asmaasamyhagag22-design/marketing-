"""Universal content-image quality gate (reel/image_quality) — hermetic, no network.

Pins the MEASURED calibration: a large real photo passes; a tiny category thumbnail / banner
strip / near-blank graphic is rejected; the URL filter keeps only usable photos (order
preserved), drops undecodable/unreachable, and respects max_keep — all via an injected fetch.
"""
from __future__ import annotations

import io

from PIL import Image

from reel.image_quality import assess_photo, filter_usable_photos, measure_bytes


def _img_bytes(w, h, color=(120, 90, 60), fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format=fmt)
    return buf.getvalue()


def test_assess_keeps_large_photo():
    ok, why = assess_photo(1600, 1066, mean_lum=120, white_pct=10)
    assert ok and why == "ok"


def test_assess_rejects_tiny_thumbnail():
    # Orange's 298x175 category thumbnail -> blurry when upscaled to 1080x1920.
    ok, why = assess_photo(298, 175)
    assert not ok and "too_small" in why


def test_assess_rejects_banner_ratio():
    # short side passes (600 >= 500) so the RATIO rule is what fires (1800/600 = 3.0).
    ok, why = assess_photo(1800, 600)
    assert not ok and "banner_ratio" in why


def test_assess_rejects_blank_and_extreme_luminance():
    assert not assess_photo(1000, 1000, white_pct=92)[0]      # near-blank
    assert not assess_photo(1000, 1000, mean_lum=5)[0]        # near-black graphic
    assert not assess_photo(1000, 1000, mean_lum=250)[0]      # near-white graphic
    assert not assess_photo(0, 0)[0]                           # no dimensions


def test_measure_bytes_reads_dimensions_and_handles_garbage():
    m = measure_bytes(_img_bytes(800, 600))
    assert m and m[0] == 800 and m[1] == 600
    assert measure_bytes(b"not an image") is None
    assert measure_bytes(b"") is None


def test_filter_keeps_only_usable_preserves_order():
    sizes = {
        "https://x/big1": (1600, 1066),    # keep
        "https://x/thumb": (298, 175),     # reject: too small
        "https://x/big2": (1000, 1000),    # keep
        "https://x/banner": (1800, 600),   # reject: banner ratio
        "https://x/dead": None,            # unreachable -> drop
    }

    def fake_fetch(url):
        sz = sizes.get(url)
        return _img_bytes(*sz) if sz else None

    out = filter_usable_photos(list(sizes.keys()), fetch=fake_fetch)
    assert out == ["https://x/big1", "https://x/big2"]


def test_filter_skips_non_http_and_respects_max_keep():
    def fake_fetch(url):
        return _img_bytes(1200, 1200)

    urls = ["data:image/png;base64,xx", "ftp://x/a", "https://x/1", "https://x/2", "https://x/3"]
    out = filter_usable_photos(urls, fetch=fake_fetch, max_keep=2)
    assert out == ["https://x/1", "https://x/2"]
