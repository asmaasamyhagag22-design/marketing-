"""Inline-svg logo rasterization — the non-browser logic (index parse, ink gate,
enrich no-op paths). The actual Playwright capture is exercised live, not in CI."""
from __future__ import annotations

import io
import json
from pathlib import Path

from scraper.inline_svg_logo import _inline_svg_index, _gate, enrich_profile_logo


def test_inline_svg_index_parses_only_pseudo_src():
    assert _inline_svg_index("inline-svg:1") == 1
    assert _inline_svg_index("inline-svg:15") == 15
    assert _inline_svg_index("https://x.com/logo.png") is None
    assert _inline_svg_index("data:image/png;base64,AAAA") is None
    assert _inline_svg_index("text-wordmark:Acme") is None
    assert _inline_svg_index("inline-svg:notanint") is None


def _png_mark(color, *, canvas=(100, 100), mark=(20, 20)):
    """A small opaque `mark` of `color` centered on a larger TRANSPARENT canvas — a
    logo-like moderate opaque fraction (here 4%)."""
    from PIL import Image
    im = Image.new("RGBA", canvas, (0, 0, 0, 0))
    block = Image.new("RGBA", mark, color)
    im.paste(block, ((canvas[0] - mark[0]) // 2, (canvas[1] - mark[1]) // 2))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _png_solid(color, size=(40, 40)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_gate_rejects_blank_and_solid_block():
    # Fully transparent -> no ink -> reject.
    assert _gate(_png_solid((0, 0, 0, 0))) is None
    # A 100%-opaque white block (Assih's failure mode) -> not a logo -> reject.
    assert _gate(_png_solid((255, 255, 255, 255))) is None


def test_gate_picks_chip_by_luminance():
    # A dark/colour logo (red mark on transparent) -> default LIGHT chip.
    assert _gate(_png_mark((230, 0, 0, 255))) is False
    # A WHITE logo (Andalusia's case) -> needs a DARK chip (recovered, not rejected).
    assert _gate(_png_mark((255, 255, 255, 255))) is True


def test_enrich_is_noop_for_non_inline_svg_logo(tmp_path: Path):
    prof = tmp_path / "p.json"
    prof.write_text(json.dumps({
        "visual": {"primary_logo": {"src": "https://x.com/logo.png"}}
    }), encoding="utf-8")
    before = prof.read_text(encoding="utf-8")
    # Even with a real HTML file, a non-inline-svg logo is left untouched.
    html = tmp_path / "home.html"
    html.write_text("<html><body><svg></svg></body></html>", encoding="utf-8")
    assert enrich_profile_logo(prof, html) is False
    assert prof.read_text(encoding="utf-8") == before          # file unchanged


def test_enrich_is_noop_when_html_missing(tmp_path: Path):
    prof = tmp_path / "p.json"
    prof.write_text(json.dumps({
        "visual": {"primary_logo": {"src": "inline-svg:1"}}
    }), encoding="utf-8")
    assert enrich_profile_logo(prof, tmp_path / "does_not_exist.html") is False
