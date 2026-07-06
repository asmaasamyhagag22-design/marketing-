"""Brand end-card design (reel/endcard.py): contrast-aware background + tone-aware typography.

Origin (owner demo feedback): the end-card rendered the brand LOGO on the brand's OWN primary
colour — a GOLD jewelry logo vanished on a gold ground ("انت بظت اللوجو") — the name was chunky
sans ("الكلام بشع"), and a fake white "Catalog" BUTTON sat in a non-interactive video ("الزار دا
إيه لازمته"). This locks the fixes without Chromium/network:
  - a light/gold/white logo -> DARK card, a dark logo -> LIGHT card (logo always has contrast);
  - luxury/fashion -> refined Fraunces serif name; else a clean sans;
  - no fake button on elegant cards — the brand URL is the real "where to go".
"""
from __future__ import annotations

from reel.endcard import (
    _endcard_html, _hex_to_rgb, _logo_mean_luma, _luma, _mix, _rgb_to_hex, _url_label,
)


def test_colour_helpers_roundtrip_and_mix():
    assert _hex_to_rgb("#CCB454") == (204, 180, 84)
    assert _hex_to_rgb("#fff") == (255, 255, 255)
    assert _hex_to_rgb("garbage") == (22, 20, 26)          # safe fallback, never raises
    assert _rgb_to_hex((204, 180, 84)) == "#ccb454"
    assert _rgb_to_hex(_mix((0, 0, 0), (255, 255, 255), 0.5)) == "#808080"
    assert _luma((255, 255, 255)) == 255.0 and _luma((0, 0, 0)) == 0.0


def test_missing_logo_defaults_to_light_so_card_is_dark():
    # honest default: no logo -> treat as light (255) -> the dark luxury card path
    assert _logo_mean_luma(None) == 255.0
    assert _logo_mean_luma("") == 255.0


def test_url_label_is_a_clean_brand_domain():
    assert _url_label({"final_url": "https://eg.azzafahmy.com/collections"}) == "azzafahmy.com"
    assert _url_label({"source_url": {"value": "http://www.orange.eg/en/"}}) == "orange.eg"
    assert _url_label({}) == ""


def test_elegant_dark_card_has_serif_and_no_fake_button():
    html = _endcard_html("data:image/png;base64,AAAA", "Azza Fahmy", "Catalog", "azzafahmy.com",
                         "#CCB454", "#BDA160", rtl=True, width=1080, height=1920,
                         elegant=True, dark=True)
    assert "Fraunces" in html                       # refined luxury serif, not chunky sans
    assert 'class="cta"' not in html                # NO fake button on an elegant card
    assert "azzafahmy.com" in html                  # the URL is the real 'where to go'
    assert "#060608" in html                        # deep charcoal ground -> the gold logo pops
    assert "halo" in html                           # brand-colour glow behind the logo
    assert ".beam" not in html                      # the old random light-beams are gone


def test_bold_light_card_has_hairline_cta_and_dark_ink():
    html = _endcard_html("data:image/png;base64,AAAA", "As-Salam", "Book now", "assih.com",
                         "#1b3a6b", "#2b4a7b", rtl=False, width=1080, height=1920,
                         elegant=False, dark=False)
    assert "Space Grotesk" in html                  # clean modern sans for a non-luxury brand
    assert 'class="cta"' in html                    # a REFINED chip (hairline), only for bold
    assert "border:1px solid" in html               # hairline, not a chunky filled pill
    assert "#2A1A1F" in html                         # dark ink on the light ground
    assert "background:#fff" not in html            # the old solid white button is gone
