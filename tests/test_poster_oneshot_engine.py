"""One-shot poster ENGINE wiring (poster/pipeline._try_oneshot) — hermetic.

Pins the pilot's promise now that it's a pipeline mode:
  * a render ships ONLY when the character-exact fidelity gate passes (rate 1.0);
  * a failing render is retried, then the engine yields None (-> classic fallback);
  * no multimodal caller / no Vertex project -> engine skipped (None) without a call;
  * the shipped result carries the audit trail + engine='oneshot' + the gated copy.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import poster.oneshot as oneshot
import poster.pipeline as pipeline
from poster.concept import CreativeConcept
from poster.from_profile import build_poster_brief


_PROFILE = {
    "name": {"value": "Daturial", "evidence": [
        {"block_id": "b", "page_url": "https://daturial.example/", "quote": "Daturial"}]},
    "languages": ["en"],
    "tagline": {"value": "Autonomous AI Systems", "evidence": [
        {"block_id": "b2", "page_url": "https://daturial.example/", "quote": "Autonomous AI Systems"}]},
    "offerings": [],
}


def _concept() -> CreativeConcept:
    return CreativeConcept(
        audience="enterprises", single_message="msg", core_benefit="benefit",
        emotional_tone="confident", visual_idea="modern tech scene",
        proof_points=[], headline="Autonomous AI Systems", subheadline="", cta="Book a Meeting")


class _VisionCaller:
    """Caller-protocol fake for the OCR read-back."""
    def __init__(self, lines):
        self._lines = lines

    def __call__(self, system, user, response_model, group_name="", images=None):
        if "lines" in getattr(response_model, "model_fields", {}):
            return response_model(lines=list(self._lines)), None   # the OCR read-back
        return response_model(), None                              # permissive QA verdict


def _run(monkeypatch, tmp_path, *, seen_lines, gen_fail=False, caller=None):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    calls = {"gen": 0}

    def fake_generate(prompt, out_path, **kw):
        calls["gen"] += 1
        if gen_fail:
            raise RuntimeError("model down")
        Path(out_path).write_bytes(b"\x89PNG fake")
        return Path(out_path)

    monkeypatch.setattr(oneshot, "generate_oneshot_poster", fake_generate)
    # The art-critic step is exercised separately; keep these unit runs OCR-only.
    import poster.pipeline as _pl
    monkeypatch.setattr(_pl, "poster_vision_qa",
                        lambda *a, **k: _pl.PosterQAVerdict(overall_pass=True, checked=True,
                                                            score=8, reason="stub"))
    brief = build_poster_brief(_PROFILE, headline_override="Autonomous AI Systems")
    brief = brief.model_copy(update={"cta_text": "Book a Meeting"})
    res = pipeline._try_oneshot(
        _PROFILE, brief, _concept(), None,
        caller if caller is not None else _VisionCaller(seen_lines),
        arabic=False, audit={"asset_type": "poster", "final_copy": {"fields": []}},
        out_dir=str(tmp_path), variation=None, max_retries=1, log=lambda m: None)
    return res, calls


def test_fidelity_pass_ships_with_audit_and_engine_tag(monkeypatch, tmp_path):
    res, calls = _run(monkeypatch, tmp_path,
                      seen_lines=["Autonomous AI Systems", "Book a Meeting"])
    assert res is not None
    assert res.engine == "oneshot"
    assert res.qa.overall_pass and res.qa.checked
    assert res.audit is not None
    assert calls["gen"] == 1
    assert Path(res.poster_path).exists()


def test_garbled_render_never_ships_and_is_retried(monkeypatch, tmp_path):
    # OCR sees an ALTERED headline every attempt -> gate fails -> None (classic fallback).
    res, calls = _run(monkeypatch, tmp_path,
                      seen_lines=["Autonomous AI System", "Book a Meeting"])  # dropped 's'... altered word
    assert res is None
    assert calls["gen"] == 2          # retried max_retries+1 times, none shipped


def test_generation_failure_degrades_to_none(monkeypatch, tmp_path):
    res, calls = _run(monkeypatch, tmp_path, seen_lines=[], gen_fail=True)
    assert res is None
    assert calls["gen"] == 2


def test_skipped_without_caller_or_project(monkeypatch, tmp_path):
    brief = build_poster_brief(_PROFILE)
    res = pipeline._try_oneshot(
        _PROFILE, brief, _concept(), None, None,   # no caller
        arabic=False, audit=None, out_dir=str(tmp_path), variation=None,
        max_retries=1, log=lambda m: None)
    assert res is None

    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    res2 = pipeline._try_oneshot(
        _PROFILE, brief, _concept(), None, _VisionCaller([]),
        arabic=False, audit=None, out_dir=str(tmp_path), variation=None,
        max_retries=1, log=lambda m: None)
    assert res2 is None


def test_painted_brand_name_on_objects_never_ships(monkeypatch, tmp_path):
    """The owner caught the model painting the brand onto an invented delivery ROBOT
    (a false visual claim). The corner logo reads as 1-2 lines; MORE brand-name lines
    mean painted branding -> that render is rejected and retried."""
    res, calls = _run(monkeypatch, tmp_path, seen_lines=[
        "Autonomous AI Systems", "Book a Meeting",
        "Daturial",              # corner logo (allowed)
        "DATURIAL",              # painted on a device
        "daturial delivery",     # painted on a vehicle
    ])
    assert res is None
    assert calls["gen"] == 2


def test_garbled_invented_labels_never_ship(monkeypatch, tmp_path):
    """Invented product packaging shows up as several junk extra lines -> rejected."""
    res, calls = _run(monkeypatch, tmp_path, seen_lines=[
        "Autonomous AI Systems", "Book a Meeting",
        "XKZPro Formula", "Vitamix Plus", "Glow Serum 3000",   # 3 fake product labels
    ])
    assert res is None
    assert calls["gen"] == 2


def test_prompt_carries_concept_and_integrity_mandates():
    from poster.oneshot import build_oneshot_prompt
    p = build_oneshot_prompt(
        {"headline": "H", "subheadline": "S", "cta": "C"},
        brand_name="Daturial", single_message="delegate whole workflows to AI workers",
        visual_idea="one confident manager and a single glowing AI colleague")
    assert "THE CONCEPT" in p and "delegate whole workflows" in p
    assert "THE SCENE" in p and "glowing AI colleague" in p
    assert "ONE clear focal subject" in p
    assert "TEXT CONTRAST" in p
    assert "BRAND INTEGRITY" in p and "NEVER paint" in p
    assert "UNLABELED" in p


def test_real_product_props_allow_their_real_labels_but_not_invented_ones(monkeypatch, tmp_path):
    """The owner's radical fix: attach the brand's REAL product photos as props — a real
    label ('بانادول اكسترا') is correct BY CONSTRUCTION and allowed; invented labels stay
    junk. Also a real bag carrying the brand name correctly is allowed."""
    import poster.pipeline as _pl
    monkeypatch.setattr(_pl, "_gather_product_props",
                        lambda profile, caller, log, product_image=None: ([(b"img", "image/jpeg")],
                                                      ["Panadol Extra 500mg", "Daturial Bag"],
                                                      "prop"))
    res, calls = _run(monkeypatch, tmp_path, seen_lines=[
        "Autonomous AI Systems", "Book a Meeting",
        "Panadol Extra 500mg",       # the attached product's REAL label -> allowed
        "Daturial Bag",              # brand on a REAL asset -> allowed (correct writing)
        "Daturial",                  # corner logo -> allowed (within the 2-line budget)
    ])
    assert res is not None and res.engine == "oneshot"

    # Invented labels (not on any attached asset) still reject the render.
    monkeypatch.setattr(_pl, "_gather_product_props",
                        lambda profile, caller, log, product_image=None: ([(b"img", "image/jpeg")],
                                                      ["Panadol Extra 500mg"], "prop"))
    res2, calls2 = _run(monkeypatch, tmp_path, seen_lines=[
        "Autonomous AI Systems", "Book a Meeting",
        "XKZ Formula", "GlowMax 3000", "Vitaboost Pro",   # 3 invented labels
    ])
    assert res2 is None


def test_gather_product_props_prioritizes_the_user_picked_product(monkeypatch):
    """When the user PICKS a product (studio RAG picker), its REAL photo becomes the PRIMARY
    composited prop so the poster SHOWS that exact product — parallel to the reel's featured image,
    and kept even if the quality gate would drop it (the user chose it)."""
    import poster.pipeline as pl
    import reel.image_quality as iq

    profile = {"visual": {"content_images": ["https://x/a.jpg", "https://x/b.jpg"]}}
    picked = "https://x/hairgrowth.jpg"                    # NOT among the scraped content_images
    monkeypatch.setattr(pl, "_image_bytes_from_url",
                        lambda u: (b"IMG:" + u.encode(), "image/jpeg"))

    # gate keeps the content images -> picked still LEADS and the set is capped at 2
    monkeypatch.setattr(iq, "filter_usable_photos", lambda urls, max_keep=2: list(urls)[:max_keep])
    props, _, role = pl._gather_product_props(profile, None, lambda m: None, product_image=picked)
    assert props[0] == (b"IMG:" + picked.encode(), "image/jpeg")   # the picked product is primary
    assert len(props) <= 2 and role == "prop"

    # even if the gate drops EVERY scraped image, the user's pick survives
    monkeypatch.setattr(iq, "filter_usable_photos", lambda urls, max_keep=2: [])
    props2, _, _r = pl._gather_product_props(profile, None, lambda m: None, product_image=picked)
    assert props2 and props2[0] == (b"IMG:" + picked.encode(), "image/jpeg")

    # no pick -> unchanged behaviour (scraped content images, in order)
    monkeypatch.setattr(iq, "filter_usable_photos", lambda urls, max_keep=2: list(urls)[:max_keep])
    props3, _, _r = pl._gather_product_props(profile, None, lambda m: None)
    assert [p[0] for p in props3] == [b"IMG:https://x/a.jpg", b"IMG:https://x/b.jpg"]


def test_service_brand_attaches_place_photos_products_attach_props(monkeypatch):
    # FIX-C2 (was: service brands attached NOTHING -> every service poster collapsed to stock).
    # A whole-brand SERVICE poster now attaches its real premises as PLACE photos; a product
    # brand still attaches props; a PICKED product always attaches with role 'prop'.
    import poster.pipeline as pl
    import reel.image_quality as iq
    monkeypatch.setattr(pl, "_image_bytes_from_url", lambda u: (b"IMG:" + u.encode(), "image/jpeg"))
    monkeypatch.setattr(iq, "filter_usable_photos", lambda urls, max_keep=2: list(urls)[:max_keep])

    service = {"category": {"value": "education"},
               "visual": {"content_images": ["https://x/campus.jpg", "https://x/lab.jpg"]}}
    props, _lines, role = pl._gather_product_props(service, None, lambda m: None)
    assert role == "place"
    assert [p[0] for p in props] == [b"IMG:https://x/campus.jpg", b"IMG:https://x/lab.jpg"]

    # a PICKED product always attaches as a PROP, even for a service brand
    props_p, _l, role_p = pl._gather_product_props(service, None, lambda m: None,
                                                   product_image="https://x/course.jpg")
    assert role_p == "prop" and props_p[0] == (b"IMG:https://x/course.jpg", "image/jpeg")

    # a PRODUCT brand attaches whole-brand props as before
    ecom = {"category": {"value": "ecommerce"}, "visual": {"content_images": ["https://x/p.jpg"]}}
    props2, _l2, role2 = pl._gather_product_props(ecom, None, lambda m: None)
    assert role2 == "prop" and props2[0] == (b"IMG:https://x/p.jpg", "image/jpeg")


def test_prompt_product_props_mode_vs_unlabeled_mode():
    from poster.oneshot import build_oneshot_prompt
    with_products = build_oneshot_prompt({"headline": "H"}, brand_name="B", n_products=2)
    assert "REAL PRODUCT PROPS" in with_products
    assert "COMPLETELY UNLABELED" not in with_products
    assert "belong to this business's real world" in with_products
    without = build_oneshot_prompt({"headline": "H"}, brand_name="B", n_products=0)
    assert "COMPLETELY UNLABELED" in without
    assert "REAL PRODUCT PROPS" not in without


def test_prompt_place_mode_and_locale_line():
    from poster.oneshot import build_oneshot_prompt
    p = build_oneshot_prompt({"headline": "H"}, brand_name="B", n_places=2,
                             locale_line="PEOPLE & SETTING — every person is from Egypt.")
    assert "REAL PLACE" in p and "Set THE SCENE inside this real place" in p
    assert "REAL PRODUCT PROPS" not in p
    assert "PEOPLE & SETTING" in p and "Egypt" in p
    # no locale evidence -> no cultural claim injected
    q = build_oneshot_prompt({"headline": "H"}, brand_name="B")
    assert "PEOPLE & SETTING" not in q and "REAL PLACE" not in q


def test_corner_placeholder_gate_detects_slot_not_light_headers(tmp_path):
    # FIX-C1: a white SLOT in the logo corner of a dark header -> detected; a legitimately
    # light full-width header -> NOT detected; a busy/gradient band -> NOT detected.
    from PIL import Image
    import poster.pipeline as pl

    W, H = 928, 1152
    # 1) navy band + white plate at the top-right (the measured nti defect)
    im = Image.new("RGB", (W, H), (16, 42, 96))
    for x in range(770, 886):
        for y in range(0, 126):
            im.putpixel((x, y), (250, 250, 250))
    p1 = tmp_path / "slot.png"; im.save(p1)
    assert pl._corner_placeholder_detected(p1, rtl=True) is True

    # 2) legitimately light header across the whole width -> median is light -> pass
    im2 = Image.new("RGB", (W, H), (16, 42, 96))
    for x in range(W):
        for y in range(0, 140):
            im2.putpixel((x, y), (245, 244, 240))
    p2 = tmp_path / "light.png"; im2.save(p2)
    assert pl._corner_placeholder_detected(p2, rtl=True) is False

    # 3) busy gradient corner -> high variance -> pass
    im3 = Image.new("RGB", (W, H), (16, 42, 96))
    for x in range(600, W):
        for y in range(0, 140):
            im3.putpixel((x, y), ((x * 7) % 256, (y * 5) % 256, 120))
    p3 = tmp_path / "busy.png"; im3.save(p3)
    assert pl._corner_placeholder_detected(p3, rtl=True) is False


def test_low_contrast_logo_gets_frosted_scrim_high_contrast_does_not(tmp_path):
    # FIX-C1b (topshoes: dark crest on dark navy header = invisible). A low-contrast
    # logo gets a soft light frosted badge behind it; a high-contrast (white) logo keeps
    # the plate-free look. Never a hard white box.
    import io
    from PIL import Image
    import poster.pipeline as pl

    W, H = 928, 1152
    def _poster(path):
        Image.new("RGB", (W, H), (18, 20, 40)).save(path)          # dark navy canvas

    def _logo_bytes(color):
        im = Image.new("RGBA", (400, 180), (0, 0, 0, 0))
        for x in range(40, 360):
            for y in range(40, 140):
                im.putpixel((x, y), (*color, 255))
        buf = io.BytesIO(); im.save(buf, format="PNG")
        return buf.getvalue()

    def scrim_band_mean(path):
        # the PAD band just left of the logo box — inside the scrim, outside the mark itself
        im = Image.open(path).convert("L")
        margin = int(W * 0.045)                       # 41
        tw = int(W * 0.22)                            # logo target width 204
        px = W - margin - tw                          # rtl -> right corner
        band = im.crop((px - 14, margin + 4, px - 2, margin + 54))
        data = list(band.getdata())
        return sum(data) / len(data)

    dark = tmp_path / "dark_logo.png"; _poster(dark)
    assert pl._overlay_real_logo(dark, _logo_bytes((25, 27, 48)), rtl=True)   # near-navy crest
    assert scrim_band_mean(dark) > 100   # frosted LIGHT badge lifted the band (canvas was ~22)

    light = tmp_path / "light_logo.png"; _poster(light)
    assert pl._overlay_real_logo(light, _logo_bytes((250, 250, 250)), rtl=True)
    assert scrim_band_mean(light) < 80   # high contrast -> NO badge; band stays navy-dark
