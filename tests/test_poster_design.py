"""Poster design-spec renderer: layout variety, no raw URL, revived hero, RTL.

These pin the 2026-06-16 redesign that moved the poster from ONE fixed bottom-block
layout (every brand identical) to a per-brand design spec, and removed the raw URL
from the creative (big-brand posters never print a link on the image).
"""
from __future__ import annotations

from poster.schemas import PosterBrief, PosterDesignSpec
from poster.from_profile import _extract_logo, build_poster_brief
from poster.template import default_design_spec, render_poster_html, _LAYOUTS
from poster.art_director import (
    build_design_spec, build_llm_concept_prompt, _DesignSpecResponse, _CreativeConceptResponse,
)
from business_profile.llm.caller import MockCaller


def _brief(name: str, headline: str = "Grow Your Business", **kw) -> PosterBrief:
    base = dict(
        business_name=name,
        category="business",
        headline=headline,
        cta_text="Learn more",
        cta_url="https://example.com/contact?utm=ad",
        palette_hex=["#e60000", "#0b1f3a"],
        primary_color="#e60000",
    )
    base.update(kw)
    return PosterBrief(**base)


def test_default_spec_varies_layout_across_brands():
    # Different brand names should not all collapse to one layout.
    names = ["Vodafone", "Telecom Egypt", "Qasr Elkbabgi", "Digilians",
             "Azza Fahmy", "NTI", "Almentor", "Zooba"]
    layouts = {default_design_spec(_brief(n)).layout for n in names}
    assert len(layouts) >= 3, f"layouts too uniform: {layouts}"


def test_default_spec_is_deterministic_per_brand():
    # Same brand -> same layout every time (consistent identity).
    a = default_design_spec(_brief("Vodafone")).layout
    b = default_design_spec(_brief("Vodafone")).layout
    assert a == b


def test_no_raw_url_on_the_poster():
    brief = _brief("Vodafone")
    html = render_poster_html(brief, density="full")
    assert brief.cta_url not in html          # the link itself is never printed
    assert "cta-url" not in html              # nor the old url span class
    assert "example.com" not in html
    # the CTA verb is still present
    assert "Learn more" in html


def test_hero_headline_revived_for_short_headline():
    spec = PosterDesignSpec(layout="magazine_hero", headline_treatment="stacked_hero")
    html = render_poster_html(_brief("Acme", headline="Bold New Ideas"), spec=spec)
    assert 'class="hero-headline' in html      # the ELEMENT, not just the CSS rule
    assert 'class="hw accent"' in html        # one word carries the brand accent


def test_long_headline_falls_back_to_block():
    spec = PosterDesignSpec(headline_treatment="stacked_hero")
    long = "We deliver enterprise grade integrated telecom solutions nationwide"
    html = render_poster_html(_brief("Acme", headline=long), spec=spec)
    assert 'class="hero-headline' not in html  # no hero ELEMENT (CSS rule may exist)
    assert 'class="headline"' in html


def test_all_layouts_render_without_error():
    for layout in _LAYOUTS:
        spec = PosterDesignSpec(layout=layout)
        html = render_poster_html(_brief("Acme"), spec=spec)
        assert "canvas" in html and "lower" in html


def test_rtl_arabic_right_aligns_and_sets_dir():
    html = render_poster_html(_brief("قصر الكبابجي", headline="ألذ مشويات مصرية"), density="full")
    assert 'dir="rtl"' in html
    assert "align-right" in html


def test_show_list_controls_visible_blocks():
    # minimal: only logo + headline + cta (no offerings/contact/social).
    brief = _brief("Acme", subheadline="we do things", offerings=["A", "B"],
                   contact_line="+20 100", )
    spec = PosterDesignSpec(show=["logo", "headline", "cta"])
    html = render_poster_html(brief, spec=spec)
    assert 'class="offerings"' not in html     # the ELEMENT (CSS rule always exists)
    assert "we do things" not in html
    # full show surfaces them
    spec_full = PosterDesignSpec(show=["logo", "headline", "sub", "offerings", "cta", "contact"])
    html_full = render_poster_html(brief, spec=spec_full)
    assert 'class="offerings"' in html_full and "we do things" in html_full


# --- STEP 2: the LLM art-director fills the design spec from the data ---

def test_build_design_spec_falls_back_without_caller():
    spec = build_design_spec(_brief("Acme"), caller=None)
    assert isinstance(spec, PosterDesignSpec)
    assert spec.layout in _LAYOUTS


def test_build_design_spec_maps_and_validates_llm_output():
    brief = _brief("Qasr Elkbabgi", headline="More than just a restaurant",
                   palette_hex=["#8B5542", "#1a1a1a"], primary_color="#8B5542",
                   logo_url="https://x/logo.png")
    resp = _DesignSpecResponse(
        layout="side_panel_right", headline_treatment="stacked_hero", accent_word="last",
        text_align="left", scrim_strength=0.7, show=["logo", "headline", "cta", "BOGUS"],
        accent_hex="#8B5542", rationale="warm grill identity",
        marketing_archetype="magazine_editorial",
        text_box=[0.52, 0.5, 0.42], logo_xy=[0.06, 0.05],
    )
    spec = build_design_spec(brief, caller=MockCaller({"poster_design": resp}))
    assert spec.layout == "side_panel_right"
    assert spec.marketing_archetype == "magazine_editorial"   # archetype mapped through
    assert spec.text_box == [0.52, 0.5, 0.42]       # FREE-FORM coords mapped through
    assert spec.logo_xy == [0.06, 0.05]
    assert spec.negative_space_zone == "right"      # derived from the free text_box (cx>0.6)
    assert "BOGUS" not in spec.show                 # unknown show item dropped
    assert spec.accent_hex == "#8B5542"             # grounded: a real brand color


def test_build_design_spec_rejects_offpalette_accent():
    brief = _brief("Acme", palette_hex=["#8B5542"], primary_color="#8B5542")
    resp = _DesignSpecResponse(
        layout="bottom_band", headline_treatment="block", accent_word="none",
        text_align="left", scrim_strength=0.8, show=["logo", "headline", "cta"],
        accent_hex="#00ff00", rationale="x",   # NOT in the brand palette
        marketing_archetype="product_hero",
        text_box=[0.06, 0.62, 0.6], logo_xy=[0.07, 0.05],
    )
    spec = build_design_spec(brief, caller=MockCaller({"poster_design": resp}))
    assert spec.accent_hex is None                  # off-palette color is not trusted


def test_background_prompt_zone_matches_layout():
    # The image's reserved calm zone follows the chosen layout (the big-brand look).
    spec = PosterDesignSpec(layout="side_panel_right", negative_space_zone="right")
    prompt = build_llm_concept_prompt(_brief("Acme"), caller=None, spec=spec)
    assert "right half" in prompt


def test_brandbook_steers_concept_to_real_brand_world():
    # UNDERSTAND -> CREATE: the BrandBook's learned photography style reaches the image
    # prompt, and the instruction flips from 'metaphor' to a fresh on-brand photo.
    from brand import BrandBook, BrandVisualIdentity
    book = BrandBook(
        business_name="Digilians",
        visual_identity=BrandVisualIdentity(
            photography_style="real young Egyptian trainees on laptops in a Cairo tech lab"),
        audience="Egyptian youth",
    )
    mock = MockCaller({"poster_concept": _CreativeConceptResponse(
        concept_title="t", image_prompt="a vivid scene")})
    build_llm_concept_prompt(_brief("Digilians"), caller=mock, brand_book=book)
    call = mock.calls[0]
    assert "real young Egyptian trainees on laptops" in call.user_prompt   # style reached the call
    assert "NOT an abstract metaphor" in call.system_prompt                # understand -> create


def test_no_brandbook_keeps_metaphor_concept():
    mock = MockCaller({"poster_concept": _CreativeConceptResponse(
        concept_title="t", image_prompt="a scene")})
    build_llm_concept_prompt(_brief("Acme"), caller=mock, brand_book=None)
    assert "metaphor" in mock.calls[0].system_prompt.lower()


def test_unique_insight_can_drive_the_headline():
    # other_unique_insights is a headline candidate (with a small bonus) — a genuine
    # edge can lead the poster when there's no stronger tagline.
    profile = {"name": {"value": "Acme Labs"}, "category": {"value": "clinic"},
               "other_unique_insights": [{"value": "The only ISO-certified lab in Cairo"}]}
    b = build_poster_brief(profile)
    assert b.headline == "The only ISO-certified lab in Cairo"


def test_variation_is_deterministic_with_seed_and_pure_design():
    from poster.variation import build_variation
    a = build_variation(7)
    b = build_variation(7)
    assert a == b                                   # same seed -> same look (reproducible)
    assert set(a) >= {"mood", "lighting", "composition", "energy"}


def test_variation_seed_varies_the_fallback_layout():
    # Same brand, different per-run seeds -> the no-LLM fallback no longer collapses to
    # ONE layout (owner: "every poster looks the same").
    from poster.variation import build_variation, variation_seed_int
    seeds = [variation_seed_int(build_variation(i)) for i in range(8)]
    layouts = {default_design_spec(_brief("Vodafone"), variation_seed=s).layout for s in seeds}
    assert len(layouts) >= 2
    # No variation -> stable per brand (backward compatible).
    assert default_design_spec(_brief("Vodafone")).layout == default_design_spec(_brief("Vodafone")).layout


def test_variation_reaches_the_concept_prompt():
    from poster.variation import build_variation
    v = build_variation(3)
    mock = MockCaller({"poster_concept": _CreativeConceptResponse(
        concept_title="t", image_prompt="a vivid scene")})
    prompt = build_llm_concept_prompt(_brief("Acme"), caller=mock, variation=v)
    assert v["mood"] in prompt                       # the run's feel reached the image prompt
    assert v["lighting"] in prompt.lower()           # the run's lighting too


def test_variation_reaches_the_design_spec_prompt():
    from poster.variation import build_variation
    resp = _DesignSpecResponse(
        layout="bottom_band", headline_treatment="block", accent_word="none",
        text_align="left", scrim_strength=0.8, show=["logo", "headline", "cta"],
        accent_hex="", rationale="x", marketing_archetype="proof_and_trust",
        text_box=[0.06, 0.62, 0.6], logo_xy=[0.07, 0.05])
    mock = MockCaller({"poster_design": resp})
    build_design_spec(_brief("Acme"), caller=mock, variation=build_variation(1))
    assert "Creative direction for THIS render" in mock.calls[0].user_prompt


def test_brand_dna_drives_the_concept_prompt():
    # The brand's LEARNED design language (from its real creatives) leads the image prompt.
    from brand.creative_dna import BrandCreativeDNA
    dna = BrandCreativeDNA(
        business_name="WE", used_vision=True,
        imagery_style="composite photography + CGI with dramatic rim light",
        color_usage="purple hero with magenta light streaks",
        signature_moves="purple light beams over a glowing cityscape",
        do_list=["lead with purple light effects"],
        dont_list=["no candid documentary photography"],
    )
    mock = MockCaller({"poster_concept": _CreativeConceptResponse(
        concept_title="t", image_prompt="a scene")})
    p = build_llm_concept_prompt(_brief("WE"), caller=mock, brand_dna=dna)
    assert "BRAND DESIGN LANGUAGE" in p
    assert "purple light beams over a glowing cityscape" in p   # signature move reached it
    # Without DNA -> the generic (de-RGB) path, no brand-language block.
    p2 = build_llm_concept_prompt(_brief("WE"), caller=mock)
    assert "BRAND DESIGN LANGUAGE" not in p2


def test_freeform_layout_bottom_anchors_to_prevent_cta_clip():
    # LAYOUT SAFETY (brief Step G): a lower text_box anchors to the BOTTOM (CTA grows up,
    # never clipped); an upper one anchors to the top; wild coords are clamped on-canvas.
    from poster.template import _freeform_lower_css, _SAFE_MARGIN
    low = _freeform_lower_css([0.1, 0.72, 0.6], 0.8, "left")
    assert f"bottom:{_SAFE_MARGIN}px" in low and "top:" not in low
    high = _freeform_lower_css([0.1, 0.08, 0.6], 0.8, "left")
    assert "top:" in high and "bottom:" not in high
    wild = _freeform_lower_css([2.0, 2.0, 5.0], 0.8, "left")   # out of range -> clamped
    assert "left:-" not in wild and "width:0px" not in wild


def test_archetype_drives_treatment_and_emerging_scrim():
    # Step 3: the marketing archetype steers the RENDERER (not the coords) — product_hero ->
    # an EMERGING feathered vertical scrim (not a hard/radial box) + generous breathing padding;
    # an editorial archetype -> the headline renders as a bold designed LOCKUP.
    brief = _brief("Acme", headline="Big Bold Sale")
    base = default_design_spec(brief)
    ph = base.model_copy(update={"marketing_archetype": "product_hero",
                                 "text_box": [0.06, 0.62, 0.86], "show": ["headline"]})
    html = render_poster_html(brief, None, ph)
    assert "linear-gradient(to top" in html       # emerging from the base, not a radial box
    assert "padding:40px 46px" in html            # generous breathing room
    me = base.model_copy(update={"marketing_archetype": "magazine_editorial",
                                 "text_box": [0.55, 0.30, 0.40], "show": ["headline"]})
    assert "lockup-headline" in render_poster_html(brief, None, me)


def test_emerging_scrim_only_for_low_or_product_hero():
    # A HIGH text block on a non-product archetype keeps the soft radial wash (no emerging).
    from poster.template import _freeform_lower_css
    high = _freeform_lower_css([0.1, 0.10, 0.6], 0.8, "left", "typographic_anchor")
    assert "radial-gradient" in high and "linear-gradient(to top" not in high
    low = _freeform_lower_css([0.1, 0.10, 0.6], 0.8, "left", "product_hero")
    assert "linear-gradient(to top" in low        # product_hero forces emerging even when high


def test_headline_override_drives_the_brief():
    # Loop closure: a content-calendar item's hook (or a trend angle) becomes the headline.
    profile = {"name": {"value": "Glamira"}, "category": {"value": "jewelry"}}
    b = build_poster_brief(profile, headline_override="Lab-Grown Diamonds, Real Sparkle")
    assert b.headline == "Lab-Grown Diamonds, Real Sparkle"
    # Empty/whitespace override is ignored -> normal verbatim selection (never blank).
    b2 = build_poster_brief(profile, headline_override="   ")
    assert b2.headline and b2.headline != "Lab-Grown Diamonds, Real Sparkle"


# ---------------------------------------------------------------------
# Logo selection: reject a low-confidence banner masquerading as the logo
# (MEASURED disaster: Vodafone's wide "Rateplans.jpg" promo, unknown_candidate
# conf 0.38, was rendered as the brand logo). The fix must NOT drop a real logo the
# scraper merely left as unknown_candidate (Qasr Elkbabgi's crest at 0.54).
# ---------------------------------------------------------------------

def _profile_with_logo(classification: str, conf: float, src: str = "https://cdn.x.com/img.png"):
    return {
        "source_url": "https://brand.example.com/",
        "visual": {"logo_candidates": [
            {"src": src, "classification": classification, "confidence": conf,
             "source_type": "logo_candidate"},
        ]},
    }


def test_low_conf_unknown_candidate_banner_rejected_falls_to_wordmark():
    # The Vodafone case: a low-conf unknown_candidate is a product banner, not a logo.
    url, text, src_type, conf = _extract_logo(
        _profile_with_logo("unknown_candidate", 0.38, "https://web.vodafone.com.eg/Rateplans.jpg"),
        "Vodafone Egypt",
    )
    assert url is None                         # rejected -> no image URL
    assert text == "Vodafone Egypt"            # clean text wordmark instead of a banner


def test_unknown_candidate_above_floor_is_kept():
    # The Qasr Elkbabgi case: a REAL logo the scraper left as unknown_candidate (0.54)
    # must survive — it's above the floor.
    url, _t, _s, conf = _extract_logo(
        _profile_with_logo("unknown_candidate", 0.54, "https://cdn.strikingly.com/crest.png"),
        "Qasr Elkbabgi",
    )
    assert url == "https://cdn.strikingly.com/crest.png"


def test_primary_brand_logo_kept_even_at_low_confidence():
    # The guard targets ONLY unknown_candidate; a positively-classified brand logo is
    # trusted at any confidence (the scraper said it IS the brand mark).
    url, *_ = _extract_logo(
        _profile_with_logo("primary_brand_logo", 0.40, "https://cdn.x.com/logo.png"),
        "Acme",
    )
    assert url == "https://cdn.x.com/logo.png"
