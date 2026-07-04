"""Brand palette from the LOGO + header + FOOTER (owner's rule) — hermetic.

The palette used to come from the page screenshot + header/nav/button/inline-SVG
signals only: a raster logo contributed NOTHING (Orange's PNG -> #FF7900 missing)
and the footer was never read, so photo colors could out-vote the real brand chrome.
"""
from __future__ import annotations

import io

from PIL import Image

from scraper.extractors.visual import (
    ColorEntry,
    _build_brand_palette,
    _logo_pixel_signals,
)


def _png_data_uri(pixels: list[tuple], size: int = 20) -> str:
    """A tiny RGBA test logo as a data: URI (no network, no SSRF guard involved)."""
    img = Image.new("RGBA", (size, size))
    img.putdata([pixels[i % len(pixels)] for i in range(size * size)])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    import base64
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def test_logo_raster_pixels_become_weighted_signals():
    # 50% brand orange, 25% white (plate — must be excluded), 25% transparent.
    orange, white, clear = (254, 95, 58, 255), (255, 255, 255, 255), (0, 0, 0, 0)
    uri = _png_data_uri([orange, orange, white, clear])
    signals = _logo_pixel_signals(uri, "https://brand.example/")
    assert signals, "expected the raster logo to yield pixel signals"
    assert all(s["role"] == "logo_raster" for s in signals)
    # Orange dominates the opaque non-white pixels -> first signal, high weight.
    assert signals[0]["color"].lower().startswith("#f")   # the orange bucket
    assert signals[0]["weight"] > 8
    assert not any(s["color"].lower() == "#ffffff" for s in signals)


def test_logo_pixel_signals_never_raise_on_junk():
    assert _logo_pixel_signals(None, "https://x.example/") == []
    assert _logo_pixel_signals("inline-svg:3", "https://x.example/") == []
    assert _logo_pixel_signals("text-wordmark:Brand", "https://x.example/") == []
    assert _logo_pixel_signals("logo.svg", "https://x.example/") == []
    assert _logo_pixel_signals("data:image/png;base64,notbase64!!!", "https://x.example/") == []


def test_logo_raster_color_wins_the_palette_over_photo_colors():
    # Screenshot dominated by photo colors (a brown + a blue, decent dominance);
    # the LOGO pixels say vivid orange. The orange must become primary.
    raw = [ColorEntry(hex="#74481c", dominance=0.4), ColorEntry(hex="#62a3c7", dominance=0.3)]
    computed = {"color_signals": [
        {"color": "#fe5f3a", "role": "logo_raster", "weight": 10},
    ]}
    palette, info = _build_brand_palette(raw, computed)
    assert palette, "expected a brand palette"
    assert palette[0].hex == "#fe5f3a"


def test_footer_background_is_a_supported_brand_source():
    # A saturated footer background (brand chrome) must survive into the palette
    # even when the screenshot never shows it prominently.
    raw = [ColorEntry(hex="#eeeeee", dominance=0.6)]
    computed = {"color_signals": [
        {"color": "#123a8f", "role": "footer", "weight": 5},
    ]}
    palette, _info = _build_brand_palette(raw, computed)
    assert any(e.hex == "#123a8f" for e in palette)
