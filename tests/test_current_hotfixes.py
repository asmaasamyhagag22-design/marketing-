from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest
from PIL import Image

from business_profile.rules.from_offerings import extract_restaurant_offerings
from business_profile.rules.from_pricing import extract_pricing_visible, pricing_extraction_note
from business_profile.schemas import SourceType
from scraper.errors import ErrorCode
from scraper.extractors.visual import build_visual_identity
from scraper.fetcher import FetchResult, _salvage_partial_dom
from scraper.schemas import (
    BoundingBox,
    FailureRecord,
    PageRecord,
    PageTier,
    PageType,
    ReadinessReport,
    RobotsRecord,
    ScrapeManifest,
    ScrapeMeta,
    Section,
    TextBlock,
)
from scraper.time_utils import utc_now
from scraper.url_utils import normalize_url


def _png(color: str = "#aca297") -> bytes:
    img = Image.new("RGB", (320, 220), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _computed(candidates=None, colors=None, site_name="QASR ELKBABGI"):
    return {
        "body_bg": "rgb(172, 162, 151)",
        "header_bg": "rgb(14, 14, 14)",
        "button_bg": "rgb(190, 145, 49)",
        "body_font": "Inter",
        "heading_font": "Lora",
        "button_font": "Inter",
        "site_name": site_name,
        "logo_candidates": candidates or [],
        "color_signals": colors or [
            {"color": "rgb(172, 162, 151)", "role": "body_bg", "weight": 1},
            {"color": "rgb(14, 14, 14)", "role": "header", "weight": 6},
            {"color": "rgb(190, 145, 49)", "role": "button", "weight": 8},
        ],
    }


def _block(bid: str, url: str, text: str, page_type: PageType = PageType.HOMEPAGE) -> TextBlock:
    return TextBlock(
        block_id=bid,
        page_url=url,
        tag="p",
        text=text,
        section=Section.MAIN,
        selector=f"p#{bid}",
        bbox=BoundingBox(x=0, y=0, width=300, height=40),
        above_fold=page_type == PageType.HOMEPAGE,
        is_link=False,
        href=None,
    )


def _page(url: str, page_type: PageType, blocks: list[TextBlock], failures=None) -> PageRecord:
    return PageRecord(
        url=url,
        final_url=url,
        http_status=200,
        fetched_at=datetime.now(timezone.utc),
        fetch_duration_ms=1000,
        page_type=page_type,
        tier=PageTier.HIGH,
        viewport_width=1366,
        viewport_height=800,
        text_blocks=blocks,
        forms=[],
        failures=failures or [],
    )


def _manifest(pages: list[PageRecord]) -> ScrapeManifest:
    home = pages[0].final_url if pages else "https://example.com/"
    return ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url=home,
            normalized_url=home,
            final_url=home,
            scraped_at=utc_now(),
            pages_attempted=len(pages),
            pages_succeeded=len(pages),
        ),
        robots=RobotsRecord(checked=True, allowed=True, robots_url=home + "robots.txt"),
        readiness=ReadinessReport(
            has_homepage=True,
            has_internal_pages=len(pages) > 1,
            has_contact_signals=False,
            has_visual_signals=False,
            has_cta_candidates=False,
            has_metadata=False,
            major_missing=[],
            ready_for_extraction=True,
        ),
        pages=pages,
    )


def test_text_wordmark_logo_can_become_primary_logo_candidate():
    candidate = {
        "src": "text-wordmark:QASR%20ELKBABGI",
        "alt": "QASR ELKBABGI",
        "text_wordmark": "QASR ELKBABGI",
        "source_type": "text_wordmark",
        "context_text": "QASR ELKBABGI navbar-brand",
        "class_id": "navbar-brand",
        "in_header": True,
        "near_nav": True,
        "in_footer": False,
        "links_to_home": True,
        "width": 180,
        "height": 36,
        "is_social": False,
        "is_hero_gallery": False,
    }
    visual = build_visual_identity(_png(), _computed([candidate]), "https://www.elkbabgi.com/")

    assert visual.primary_logo is not None
    assert visual.primary_logo.source_type == "text_wordmark"
    assert visual.primary_logo.text_wordmark == "QASR ELKBABGI"
    assert visual.logo is None  # legacy image-logo field should not fake an image URL


def test_no_confident_primary_logo_but_candidates_are_preserved():
    visual = build_visual_identity(
        _png(),
        _computed([{
            "src": "https://example.com/favicon.ico",
            "alt": "favicon",
            "source_type": "favicon",
            "context_text": "favicon",
            "class_id": "",
            "in_header": False,
            "near_nav": False,
            "in_footer": False,
            "links_to_home": False,
            "width": 16,
            "height": 16,
            "is_social": False,
            "is_hero_gallery": False,
        }]),
        "https://example.com/",
    )

    assert visual.primary_logo is None
    assert len(visual.logo_candidates) == 1
    assert visual.visual_extraction_note == "no_confident_primary_logo"


def test_menu_page_exists_but_prices_not_text_extracted_stays_unknown():
    home = "https://restaurant.example/"
    menu = home + "menu/"
    m = _manifest([
        _page(home, PageType.HOMEPAGE, [_block("home1", home, "Authentic Egyptian Cuisine")]),
        _page(menu, PageType.MENU, [_block("menu1", menu, "Our Menu: grilled dishes and stews", PageType.MENU)]),
    ])

    pricing = extract_pricing_visible(m)

    assert pricing.value is None
    assert pricing.source_type == SourceType.MISSING
    assert pricing_extraction_note(m) == "menu_page_found_but_prices_not_text_extracted"


def test_menu_timeout_with_partial_dom_is_salvaged_and_marked_as_warning():
    class FakePage:
        url = "https://restaurant.example/menu/"

        def content(self):
            return "<html><body><h1>Our Menu</h1><p>grilled dishes and stews</p></body></html>"

        def evaluate(self, _script):
            return "Our Menu\ngrilled dishes and stews"

        def screenshot(self, *_, **__):
            return b"pngbytes"

    result = FetchResult(
        url="https://restaurant.example/menu/",
        final_url="https://restaurant.example/menu/",
        http_status=None,
        fetched_at=utc_now(),
        duration_ms=0,
    )

    assert _salvage_partial_dom(FakePage(), result, "navigation timeout") is True
    assert result.ok is True
    assert result.partial_content is True
    assert "timeout_partial_content_salvaged" in (result.partial_reason or "")
    assert "grilled dishes" in result.rendered_text


def test_restaurant_offerings_extracted_from_menu_and_about_text():
    home = "https://restaurant.example/"
    menu = home + "menu/"
    m = _manifest([
        _page(home, PageType.HOMEPAGE, [
            _block("home1", home, "Authentic Egyptian Cuisine since 1992"),
            _block("home2", home, "Famous for grilled meats and traditional Eastern dishes."),
        ]),
        _page(menu, PageType.MENU, [
            _block("menu1", menu, "Our special menu includes stews and family dining options.", PageType.MENU),
        ]),
    ])

    names = [o.name for o in extract_restaurant_offerings(m)]

    assert "Authentic Egyptian Cuisine" in names
    assert "Grilled Dishes" in names
    assert "Traditional Eastern Dishes" in names
    assert "Traditional Stews" in names


def test_beige_background_must_not_become_primary_brand_color():
    visual = build_visual_identity(_png("#aca297"), _computed(), "https://www.elkbabgi.com/")

    assert visual.primary_brand_color != "#aca297"
    assert "palette_dominated_by_background" in visual.visual_warnings


def test_black_gold_brown_restaurant_palette_is_preserved():
    visual = build_visual_identity(_png("#aca297"), _computed(), "https://www.elkbabgi.com/")
    brand = [c.hex for c in visual.brand_palette]

    assert "#0e0e0e" in brand
    assert "#be9131" in brand
    assert visual.primary_brand_color in {"#0e0e0e", "#be9131"}


def test_malformed_concatenated_input_url_is_rejected():
    with pytest.raises(ValueError, match="multiple absolute URLs"):
        normalize_url("https://www.elkbabgi.com/https://www.digilians.gov.eg/")
