from __future__ import annotations

import io

from PIL import Image

from business_profile.quality import compute_quality
from business_profile.rules.from_visual import extract_visual
from business_profile.schemas import (
    BusinessProfile,
    AudienceType,
    Confidence,
    ContactChannels,
    EvidencedField,
    ExtractionMeta,
    PricingPosture,
    ProfileQuality,
    SourceType,
    ToneOfVoice,
    VisualIdentitySummary,
)
from scraper.extractors.visual import build_visual_identity


def _png(color: str = "#f4ead8") -> bytes:
    img = Image.new("RGB", (300, 220), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _computed(candidates=None, colors=None, site_name="El Kbabgi Restaurant"):
    return {
        "body_bg": "rgb(244, 234, 216)",
        "header_bg": "rgb(14, 14, 14)",
        "button_bg": "rgb(190, 145, 49)",
        "body_font": "Inter",
        "heading_font": "Lora",
        "button_font": "Inter",
        "site_name": site_name,
        "logo_candidates": candidates or [],
        "color_signals": colors or [
            {"color": "rgb(244, 234, 216)", "role": "body_bg", "weight": 1},
            {"color": "rgb(14, 14, 14)", "role": "header", "weight": 6},
            {"color": "rgb(190, 145, 49)", "role": "button", "weight": 8},
        ],
    }


def _candidate(src, *, alt="Logo", source_type="img", in_header=True, near_nav=True,
               links_to_home=True, width=180, height=70, context="brand logo",
               is_social=False, is_hero_gallery=False, in_footer=False):
    return {
        "src": src,
        "alt": alt,
        "source_type": source_type,
        "context_text": context,
        "class_id": context,
        "in_header": in_header,
        "near_nav": near_nav,
        "in_footer": in_footer,
        "links_to_home": links_to_home,
        "width": width,
        "height": height,
        "is_social": is_social,
        "is_hero_gallery": is_hero_gallery,
    }


def test_nti_like_svg_lazy_or_header_logo_is_preserved_as_candidate_and_primary():
    candidates = [
        _candidate(
            "https://nti.example/assets/nti-logo.svg",
            alt="NTI logo",
            source_type="svg_file",
            context="header brand logo nti",
        ),
        _candidate(
            "https://nti.example/assets/lazy-logo.png",
            alt="",
            source_type="lazy_img",
            context="header logo data-src nti",
        ),
    ]
    v = build_visual_identity(_png(), _computed(candidates, site_name="NTI"), "https://nti.example/")

    assert len(v.logo_candidates) == 2
    assert v.primary_logo is not None
    assert v.primary_logo.src.endswith("nti-logo.svg")
    assert v.logo is not None  # backward-compatible legacy field
    assert "no_confident_primary_logo" not in v.visual_warnings


def test_digilians_like_multiple_authority_partner_logos_sets_cobranding_warning():
    candidates = [
        _candidate(
            "https://digilians.example/digilians-logo.png",
            alt="Digilians logo",
            context="header digilians brand logo",
        ),
        _candidate(
            "https://digilians.example/ministry-logo.png",
            alt="Ministry of Communications logo",
            context="header ministry government authority logo",
        ),
        _candidate(
            "https://digilians.example/partner-logo.png",
            alt="Partner logo",
            context="header partner sponsor logo",
        ),
    ]
    v = build_visual_identity(_png(), _computed(candidates, site_name="Digilians"), "https://digilians.example/")

    assert v.primary_logo is not None
    assert "digilians-logo" in v.primary_logo.src
    assert len(v.authority_logos) == 1
    assert len(v.partner_logos) == 1
    assert v.co_branding_detected is True
    assert "co_branding_detected" in v.visual_warnings


def test_social_icons_and_hero_banners_are_not_selected_as_primary_logo():
    candidates = [
        _candidate(
            "https://x.example/instagram.svg",
            alt="Instagram",
            source_type="svg_file",
            context="header social instagram icon",
            is_social=True,
            width=24,
            height=24,
        ),
        _candidate(
            "https://x.example/hero-banner.jpg",
            alt="Hero banner",
            context="hero banner slider gallery",
            is_hero_gallery=True,
            width=1200,
            height=600,
        ),
    ]
    v = build_visual_identity(_png(), _computed(candidates, site_name="Unknown"), "https://x.example/")

    assert v.primary_logo is None
    assert v.logo is None
    assert v.visual_extraction_note == "no_confident_primary_logo"
    assert "no_confident_primary_logo" in v.visual_warnings


def test_background_dominant_palette_does_not_override_black_gold_restaurant_brand():
    v = build_visual_identity(
        _png("#f4ead8"),
        _computed(site_name="El Kbabgi Restaurant"),
        "https://elkbabgi.example/",
    )

    assert v.raw_palette
    assert v.brand_palette
    assert v.primary_brand_color in {"#0e0e0e", "#be9131"}
    assert "#be9131" in [c.hex for c in v.brand_palette]
    assert "palette_dominated_by_background" in v.visual_warnings


def test_low_confidence_candidates_keep_candidates_and_note_no_confident_primary():
    candidates = [
        _candidate(
            "https://example.com/favicon.ico",
            alt="icon",
            source_type="favicon",
            in_header=False,
            near_nav=False,
            links_to_home=False,
            width=16,
            height=16,
            context="favicon",
        )
    ]
    v = build_visual_identity(_png(), _computed(candidates, site_name="Example"), "https://example.com/")

    assert v.primary_logo is None
    assert len(v.logo_candidates) == 1
    assert v.logo_candidates[0].classification == "favicon"
    assert v.visual_extraction_note == "no_confident_primary_logo"


def test_business_profile_visual_projection_keeps_old_and_new_fields():
    from scraper.schemas import ReadinessReport, RobotsRecord, ScrapeManifest, ScrapeMeta
    from scraper.time_utils import utc_now

    candidates = [_candidate("https://brand.example/logo.svg", alt="Brand logo", context="brand logo")]
    visual = build_visual_identity(_png(), _computed(candidates, site_name="Brand"), "https://brand.example/")
    manifest = ScrapeManifest(
        scrape_meta=ScrapeMeta(input_url="https://brand.example", normalized_url="https://brand.example", scraped_at=utc_now()),
        robots=RobotsRecord(checked=False, allowed=True),
        readiness=ReadinessReport(
            has_homepage=True,
            has_internal_pages=False,
            has_contact_signals=False,
            has_visual_signals=True,
            has_cta_candidates=False,
            has_metadata=True,
            ready_for_extraction=True,
        ),
        visual=visual,
    )

    summary = extract_visual(manifest)

    assert summary.logo_url == summary.primary_logo.src
    assert summary.palette_hex == summary.brand_palette
    assert summary.primary_color == summary.primary_brand_color
    assert summary.logo_candidates
    assert summary.raw_palette


def _field(value, source=SourceType.EXTRACTED):
    return EvidencedField(value=value, source_type=source, confidence=Confidence.HIGH, evidence=[])


def _quality_placeholder():
    return ProfileQuality(
        has_name=False,
        has_category=False,
        has_offerings=False,
        has_audience=False,
        has_value_propositions=False,
        has_tone=False,
        has_contact=False,
        has_visual=False,
        fields_extracted=0,
        fields_inferred=0,
        fields_missing=20,
        major_missing=[],
        ready_for_strategy=False,
    )


def test_old_visual_fields_still_work_for_backward_compatibility():
    profile = BusinessProfile(
        source_url="https://legacy.example",
        final_url="https://legacy.example",
        name=_field("Legacy Brand"),
        tagline=_field("A useful tagline"),
        description=_field("A useful brand description."),
        category=_field("restaurant"),
        offerings=[],
        pricing_visible=_field(False),
        pricing_posture=_field(PricingPosture.UNKNOWN),
        audience_type=_field(AudienceType.B2C),
        audience_signals=[],
        value_propositions=[_field("Warm family dining")],
        tone_of_voice=_field(ToneOfVoice.FRIENDLY),
        locations=[],
        service_areas=[],
        languages=[],
        hours=None,
        contact_channels=ContactChannels(phones_e164=["+201000000000"]),
        existing_ctas=[],
        social_presence=[],
        trust_signals=[],
        visual=VisualIdentitySummary(palette_hex=["#111111"], logo_url=None),
        extraction_meta=ExtractionMeta(manifest_path="m.json", extracted_at="2026-05-17T00:00:00Z"),
        quality=_quality_placeholder(),
    )

    q = compute_quality(profile)

    assert q.has_visual is True
    assert q.ready_for_poster is True
    assert "no_visual_signals" not in q.poster_blockers

def test_elkbabgi_real_palette_does_not_choose_beige_background_as_primary():
    from scraper.extractors.visual import _build_brand_palette
    from scraper.schemas import ColorEntry

    raw_palette = [
        ColorEntry(hex="#d0cfcc", dominance=0.5116),
        ColorEntry(hex="#aca297", dominance=0.3402),
        ColorEntry(hex="#171818", dominance=0.1115),
        ColorEntry(hex="#cba656", dominance=0.0271),
        ColorEntry(hex="#7e4d34", dominance=0.0097),
    ]

    brand_palette, info = _build_brand_palette(
        raw_palette,
        {
            "color_signals": [
                {"color": "#f0f0f0", "role": "button", "weight": 8}
            ]
        },
    )

    brand_hex = [c.hex for c in brand_palette]

    assert info["primary_brand_color"] != "#aca297"
    assert "#aca297" in info["background_colors"]
    assert "#cba656" in brand_hex
    assert "#7e4d34" in brand_hex
    assert "#171818" in brand_hex
    assert info["background_dominance"] >= 0.65