"""Hermetic tests for the ADAPTIVE brand-anchored background selector in poster.pipeline
(no live Vertex / network — providers, fetch and the text-to-image fn are injected). The live
edit calls are verified out-of-CI by the 2026-06-27 validation."""
import io

from PIL import Image

from poster.pipeline import (
    _best_usable_photo, _brand_style_refs, _generate_background,
    _trim_letterbox, _dna_wants_lockup,
)
from poster.template import _headline_block, default_design_spec, render_poster_html
from poster.schemas import PosterBrief


def _lockup_brief(headline="Bold Brave New"):
    return PosterBrief(business_name="WE", category="telecom", headline=headline,
                       cta_text="Learn more", cta_url="https://example.com",
                       palette_hex=["#6a2bd9", "#c81e8a"], primary_color="#6a2bd9")


def _png(w, h):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), (120, 90, 60)).save(b, "PNG")
    return b.getvalue()


class _DNA:
    def __init__(self, refs):
        self.references_seen = refs


class _FakeEdit:
    """Records calls; outpaint/style either return a path or raise (per flags)."""
    def __init__(self, outpaint_ok=True, style_ok=True):
        self.outpaint_ok, self.style_ok = outpaint_ok, style_ok
        self.calls = []

    def outpaint(self, base, prompt="", **kw):
        self.calls.append(("outpaint", base))
        if not self.outpaint_ok:
            raise RuntimeError("outpaint boom")
        return "OUT.png"

    def style(self, prompt, refs, **kw):
        self.calls.append(("style", tuple(refs)))
        if not self.style_ok:
            raise RuntimeError("style boom")
        return "STYLE.png"


def _t2i(prompt):
    return "T2I.png", "imagen-4.0"


# ---- asset selection helpers -------------------------------------------------

def test_brand_style_refs_prefers_real_ads_then_site_photos_capped():
    prof = {"visual": {"content_images": ["https://site/a.jpg", "https://site/b.jpg"]}}
    dna = _DNA(["https://ads/1.png", "https://ads/2.png", "https://ads/3.png"])
    refs = _brand_style_refs(prof, dna)
    assert refs == ["https://ads/1.png", "https://ads/2.png"]          # ads first, capped at 2
    # no dna -> falls back to the brand's own site photos
    assert _brand_style_refs(prof, None) == ["https://site/a.jpg", "https://site/b.jpg"]
    # nothing -> empty (cascade will use text-to-image)
    assert _brand_style_refs({}, None) == []


def test_best_usable_photo_uses_quality_gate_with_injected_fetch():
    prof = {"visual": {"content_images": ["https://x/tiny.png", "https://x/good.png"]}}
    big = _png(800, 1000)
    fetch = lambda u: big if u.endswith("good.png") else _png(40, 40)  # only good.png passes
    assert _best_usable_photo(prof, fetch=fetch) == "https://x/good.png"
    # all too small -> None
    assert _best_usable_photo(prof, fetch=lambda u: _png(40, 40)) is None
    assert _best_usable_photo({}, fetch=fetch) is None


# ---- the cascade -------------------------------------------------------------

def _prof_with_photo():
    return {"visual": {"content_images": ["https://x/good.png"]}}


def _good_fetch(u):
    return _png(800, 1000)


def test_cascade_outpaints_when_usable_photo():
    edit = _FakeEdit()
    path, model = _generate_background(_prof_with_photo(), None, "p",
                                       fetch=_good_fetch, edit_provider=edit, t2i=_t2i)
    assert path == "OUT.png" and model.endswith("/outpaint")
    assert edit.calls == [("outpaint", "https://x/good.png")]   # style/t2i not reached


def test_cascade_falls_to_style_when_outpaint_fails():
    edit = _FakeEdit(outpaint_ok=False)
    dna = _DNA(["https://ads/1.png"])
    path, model = _generate_background(_prof_with_photo(), dna, "p",
                                       fetch=_good_fetch, edit_provider=edit, t2i=_t2i)
    assert path == "STYLE.png" and model.endswith("/style")
    assert ("outpaint", "https://x/good.png") in edit.calls
    # style refs = the real ad FIRST, then the brand's own site photo (both real, capped at 2)
    style_calls = [c for c in edit.calls if c[0] == "style"]
    assert style_calls and style_calls[-1][1][0] == "https://ads/1.png"


def test_cascade_styles_when_no_photo_but_refs():
    edit = _FakeEdit()
    dna = _DNA(["https://ads/1.png"])
    path, model = _generate_background({}, dna, "p", edit_provider=edit, t2i=_t2i)
    assert path == "STYLE.png" and model.endswith("/style")


def test_cascade_text_to_image_when_no_assets():
    edit = _FakeEdit()
    path, model = _generate_background({}, None, "p", edit_provider=edit, t2i=_t2i)
    assert path == "T2I.png" and model == "imagen-4.0"
    assert edit.calls == []   # no edit attempted


def test_cascade_text_to_image_when_both_edit_modes_fail():
    # a usable photo is ALSO a style ref, so reaching text-to-image needs BOTH modes to fail
    edit = _FakeEdit(outpaint_ok=False, style_ok=False)
    path, model = _generate_background(_prof_with_photo(), None, "p",
                                       fetch=_good_fetch, edit_provider=edit, t2i=_t2i)
    assert path == "T2I.png" and model == "imagen-4.0"
    assert [c[0] for c in edit.calls] == ["outpaint", "style"]   # both tried, then fell through


# ---- letterbox fix -----------------------------------------------------------

def test_trim_letterbox_crops_black_bars(tmp_path):
    im = Image.new("RGB", (400, 600), (0, 0, 0))
    im.paste(Image.new("RGB", (400, 300), (110, 60, 180)), (0, 150))   # colored band in the middle
    p = tmp_path / "bg.png"; im.save(p)
    _trim_letterbox(str(p))
    out = Image.open(p)
    assert out.size[1] < 600                       # the black bars were cropped away
    assert out.getpixel((10, 10))[2] > 100         # top-left is now the band colour, not black


def test_trim_letterbox_noop_on_full_frame(tmp_path):
    im = Image.new("RGB", (400, 500), (90, 120, 150)); p = tmp_path / "f.png"; im.save(p)
    _trim_letterbox(str(p))
    assert Image.open(p).size == (400, 500)         # nothing to crop -> unchanged


# ---- DNA-driven typography ---------------------------------------------------

def test_dna_wants_lockup_detects_bold_graphic_character():
    class Bold:
        typographic_character = "extremely bold, custom-designed, heavy outlines, internal gradients"
        signature_moves = ""
    class Thin:
        typographic_character = "thin, understated, functional sans-serif"
        signature_moves = "minimalist restraint"
    assert _dna_wants_lockup(Bold()) is True
    assert _dna_wants_lockup(Thin()) is False
    assert _dna_wants_lockup(None) is False


def test_lockup_headline_is_gradient_outline_lockup():
    brief = _lockup_brief("Bold Brave New")
    html = _headline_block(brief, rtl=False, treatment="lockup", accent_word="last", column_px=900)
    assert "lockup-headline" in html
    assert html.count('class="lw') == 3            # one stacked span per word
    assert 'class="lw accent"' in html             # the last word is the accent gradient
    spec = default_design_spec(brief).model_copy(
        update={"headline_treatment": "lockup", "show": ["headline"]})
    rendered = render_poster_html(brief, None, spec)
    assert "lockup-headline" in rendered and "-webkit-text-stroke" in rendered
