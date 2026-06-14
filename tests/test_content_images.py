"""CONTENT image extraction — the brand's REAL on-page photos.

The old extractor read only <img src> and captured the logo, throwing every photo
away (MEASURED on elkbabgi: 1 of 27 images kept). Modern sites (Strikingly, Wix,
Squarespace) serve photos as CSS backgrounds (style background-image, data-bg) and
lazy data-src, mostly protocol-relative. These tests lock in that those are now
collected as ImageRole.CONTENT, while logos / icons / svg / chrome stay excluded.
"""
from __future__ import annotations

from scraper.extractors.images import extract_images_of_interest
from scraper.schemas import ImageRole

PAGE = "https://shop.example/"


def _content(html: str) -> list[str]:
    imgs = extract_images_of_interest(html, PAGE, None)
    return [i.src for i in imgs if i.role == ImageRole.CONTENT]


def test_collects_css_background_and_lazy_and_protocol_relative():
    html = (
        '<header><img src="/logo.png" alt="Company logo"></header>'
        '<section>'
        '  <img data-src="//cdn.example/photos/food1.jpeg">'          # lazy + protocol-relative
        '  <div style="background-image:url(\'/photos/interior.jpg\')"></div>'  # CSS bg
        '  <div data-bg="//cdn.example/photos/team.jpeg"></div>'      # lazy CSS bg
        '</section>'
    )
    content = _content(html)
    assert "https://cdn.example/photos/food1.jpeg" in content
    assert "https://shop.example/photos/interior.jpg" in content
    assert "https://cdn.example/photos/team.jpeg" in content


def test_excludes_logos_icons_svg_and_header_chrome():
    html = (
        '<header><img src="//cdn.example/brand-logo.png" alt="Logo"></header>'
        '<nav><div style="background-image:url(/nav-icon.png)"></div></nav>'
        '<main>'
        '  <img src="//cdn.example/assets/favicon-32.png">'          # icon marker
        '  <img src="//cdn.example/decor.svg">'                       # vector
        '  <img data-src="//cdn.example/real-dish.jpeg">'            # the one real photo
        '</main>'
        '<footer><div data-bg="//cdn.example/footer-logo.png"></div></footer>'
    )
    content = _content(html)
    assert content == ["https://cdn.example/real-dish.jpeg"]


def test_dedups_cdn_transform_variants_by_filename():
    # Same photo served at two transform sizes -> one CONTENT entry.
    html = (
        '<section>'
        '  <div data-bg="//cdn.example/img/upload/h_630,w_1200/962275_444653.jpeg"></div>'
        '  <img data-src="//cdn.example/img/upload/h_1500,w_2000/962275_444653.jpeg">'
        '</section>'
    )
    assert len(_content(html)) == 1


def test_empty_html_returns_no_content():
    assert _content("") == []
