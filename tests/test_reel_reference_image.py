"""Reel #4 — reference-image (Veo image-to-video) grounding.

Hermetic: no network, no Veo, no real ffmpeg/Chromium. Verifies the wiring that
carries a SCRAPED brand photo from the manifest -> profile -> storyboard -> the
video provider's image-to-video seed, and that it's seeded only on the brand
bookends (intro/outro).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scraper.schemas import ImageOfInterest, ImageRole

from business_profile.rules.from_visual import _hero_image_url
from poster.schemas import PosterBrief
from reel.schemas import ReelScene, Storyboard
from reel.storyboard import _reference_image_url, build_storyboard
from reel.video_provider import StubVideoProvider, _load_reference_image, _mime_for


# ---------------------------------------------------------------------
# Surfacing the hero onto the profile (business_profile/rules/from_visual)
# ---------------------------------------------------------------------

def _img(role, src, above_fold=False):
    return ImageOfInterest(role=role, src=src, page_url="https://x.com/", above_fold=above_fold)


def test_hero_prefers_above_fold_then_hero_then_og():
    m = SimpleNamespace(images_of_interest=[
        _img(ImageRole.LOGO, "https://x.com/logo.png", above_fold=True),
        _img(ImageRole.OG_IMAGE, "https://x.com/og.jpg"),
        _img(ImageRole.HERO, "https://x.com/hero-below.jpg", above_fold=False),
        _img(ImageRole.HERO, "https://x.com/hero-above.jpg", above_fold=True),
    ])
    # Above-the-fold HERO wins; the LOGO is never used as a reference photo.
    assert _hero_image_url(m) == "https://x.com/hero-above.jpg"


def test_hero_falls_back_to_og_then_none():
    only_og = SimpleNamespace(images_of_interest=[_img(ImageRole.OG_IMAGE, "https://x.com/og.jpg")])
    assert _hero_image_url(only_og) == "https://x.com/og.jpg"

    logo_only = SimpleNamespace(images_of_interest=[_img(ImageRole.LOGO, "https://x.com/logo.png")])
    assert _hero_image_url(logo_only) is None

    assert _hero_image_url(SimpleNamespace(images_of_interest=[])) is None


def test_hero_skips_non_http_src():
    m = SimpleNamespace(images_of_interest=[_img(ImageRole.HERO, "data:image/png;base64,AAAA", above_fold=True)])
    assert _hero_image_url(m) is None


# ---------------------------------------------------------------------
# Storyboard carries the photo seed (and only a photo, never a logo)
# ---------------------------------------------------------------------

def test_storyboard_seeds_reference_from_hero():
    brief = PosterBrief(business_name="Qasr Elkbabgi", headline="Authentic grills")
    profile = {"visual": {"hero_image_url": "https://x.com/hero.jpg", "logo_url": "https://x.com/logo.png"}}
    sb = build_storyboard(brief, profile=profile, caller=None, max_total_s=20.0)
    assert sb.reference_image_url == "https://x.com/hero.jpg"


def test_storyboard_reference_none_without_hero():
    # A logo present but no hero photo -> no Veo seed (logos make poor i2v seeds).
    assert _reference_image_url({"visual": {"logo_url": "https://x.com/logo.png"}}) is None
    assert _reference_image_url({"visual": {"hero_image_url": "data:image/png;base64,AA"}}) is None
    assert _reference_image_url({}) is None


# ---------------------------------------------------------------------
# The reference-image loader (SSRF guard + local file + mime)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "http://localhost/x.png", "http://127.0.0.1/a.jpg",
    "http://169.254.169.254/meta", "file:///etc/passwd", "ftp://h/x.png", "junk",
])
def test_loader_blocks_ssrf_and_junk(bad):
    assert _load_reference_image(bad) is None


def test_loader_reads_local_file(tmp_path: Path):
    p = tmp_path / "hero.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    got = _load_reference_image(str(p))
    assert got is not None
    data, mime = got
    assert data and mime == "image/png"


def test_mime_rejects_svg():
    assert _mime_for("image/svg+xml", "x.svg") is None
    assert _mime_for("", "photo.jpg") == "image/jpeg"


def test_stub_provider_accepts_reference_image_kwarg():
    import inspect
    assert "reference_image" in inspect.signature(StubVideoProvider.generate).parameters


def test_vertical_seed_reframes_landscape_to_9x16():
    """A landscape seed is reframed to 9:16 so Veo i2v outputs full-frame (no bars)."""
    import io
    from PIL import Image
    from reel.video_provider import _to_vertical_seed
    buf = io.BytesIO()
    Image.new("RGB", (1600, 900), (180, 90, 40)).save(buf, format="JPEG")
    out, mime = _to_vertical_seed(buf.getvalue())
    w, h = Image.open(io.BytesIO(out)).size
    assert mime == "image/jpeg"
    assert abs((w / h) - (9 / 16)) < 0.01


# ---------------------------------------------------------------------
# Compositor seeds ONLY the brand bookends (intro + outro)
# ---------------------------------------------------------------------

class _RecordingProvider:
    name = "fake"

    def __init__(self):
        self.seen: list[tuple[str, object]] = []

    def generate(self, prompt, *, out_path, duration_s, width, height,
                 palette=None, reference_image=None):
        self.seen.append((prompt, reference_image))
        Path(out_path).write_bytes(b"\x00")
        return Path(out_path)


def test_compositor_seeds_only_intro_and_outro(tmp_path: Path, monkeypatch):
    import reel.compositor as comp

    scenes = [
        ReelScene(kind="intro", duration_s=2.0, visual_prompt="INTRO"),
        ReelScene(kind="offering", duration_s=2.0, visual_prompt="OFFER"),
        ReelScene(kind="contact", duration_s=2.0, visual_prompt="CONTACT"),
        ReelScene(kind="outro", duration_s=2.0, visual_prompt="OUTRO"),
    ]
    sb = Storyboard(
        business_name="Qasr Elkbabgi", scenes=scenes,
        reference_image_url="https://x.com/hero.jpg", palette_hex=["#8B5542"],
        total_duration_s=8.0,
    )

    # Stub out the heavy collaborators: no Chromium text render, no real ffmpeg.
    def _fake_text_layers(storyboard, *, width, height, out_dir, include_logo=True):
        out = []
        for i in range(len(storyboard.scenes)):
            p = Path(out_dir) / f"t{i}.png"
            p.write_bytes(b"\x00")
            out.append(p)
        return out

    def _fake_run_ffmpeg(args, **kwargs):
        Path(args[-1]).write_bytes(b"\x00")  # the output path is always the last arg
        return None

    monkeypatch.setattr(comp, "render_text_layers", _fake_text_layers)
    monkeypatch.setattr(comp, "run_ffmpeg", _fake_run_ffmpeg)

    provider = _RecordingProvider()
    comp.render_reel(sb, provider=provider, out_path=tmp_path / "out.mp4", scale=0.25)

    seeded = {prompt: ref for prompt, ref in provider.seen}
    assert seeded["INTRO"] == "https://x.com/hero.jpg"
    assert seeded["OUTRO"] == "https://x.com/hero.jpg"
    assert seeded["OFFER"] is None
    assert seeded["CONTACT"] is None
