"""BrandBook — one-time multimodal brand understanding. No network in tests:
the image fetcher is injected and the caller is a MockCaller (vision ignored)."""
from __future__ import annotations

from brand import build_brand_book, save_brand_book, load_brand_book, BrandBook
from brand.brand_book import _BrandBookResponse
from business_profile.llm.caller import MockCaller


_PROFILE = {
    "name": "Digilians",
    "category": "education",
    "tone_of_voice": "credible, aspirational",
    "audience_type": "Egyptian youth",
    "tagline": "الرواد الرقميون",
    "visual": {
        "palette_hex": ["#133B66", "#B19257"],
        "primary_color": "#133B66",
        "content_images": [
            {"src": "https://www.digilians.gov.eg/assets/Landing/aboutImage1.jpeg"},
            {"src": "https://www.digilians.gov.eg/assets/Landing/3.jpeg"},
        ],
    },
}


def _fake_fetch(urls, **kw):
    # pretend each URL fetched as a tiny JPEG (bytes content is irrelevant to MockCaller)
    return [(u, b"\xff\xd8\xff", "image/jpeg") for u in urls]


def test_profile_only_book_without_caller():
    book = build_brand_book(_PROFILE, caller=None)
    assert isinstance(book, BrandBook)
    assert book.used_vision is False
    assert book.palette_hex == ["#133B66", "#B19257"]
    assert book.audience == "Egyptian youth"


def test_vision_book_maps_response_and_picks_real_bg():
    resp = _BrandBookResponse(
        aesthetic="clean institutional tech", mood="aspirational",
        color_story="navy leads with gold accent", typography_character="modern sans",
        photography_style="real classrooms and trainees",
        best_background_index=1, best_background_reason="a real training scene",
        recommended_text_color="light", voice="motivational, national",
        audience="Egyptian youth", positioning="presidential digital-skills initiative",
    )
    book = build_brand_book(
        _PROFILE, caller=MockCaller({"brand_book": resp}),
        with_research=False, _image_fetcher=_fake_fetch,
    )
    assert book.used_vision is True
    assert len(book.images_seen) == 2
    # index 1 -> the second content image is the chosen background
    assert book.visual_identity.best_background_image_url.endswith("3.jpeg")
    assert book.visual_identity.recommended_text_color == "light"
    assert book.visual_identity.photography_style == "real classrooms and trainees"
    assert book.positioning.startswith("presidential")


def test_vision_index_minus_one_means_generate():
    resp = _BrandBookResponse(
        aesthetic="x", mood="x", color_story="x", typography_character="x",
        photography_style="x", best_background_index=-1, best_background_reason="no good photo",
        recommended_text_color="dark", voice="x", audience="x", positioning="x",
    )
    book = build_brand_book(
        _PROFILE, caller=MockCaller({"brand_book": resp}),
        with_research=False, _image_fetcher=_fake_fetch,
    )
    assert book.visual_identity.best_background_image_url is None
    assert book.visual_identity.recommended_text_color == "dark"


def test_save_and_load_round_trip(tmp_path):
    book = build_brand_book(_PROFILE, caller=None)
    p = save_brand_book(book, tmp_path / "bb.json")
    again = load_brand_book(p)
    assert again.business_name == book.business_name
    assert again.palette_hex == book.palette_hex
