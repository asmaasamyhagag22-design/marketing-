# -*- coding: utf-8 -*-
"""Seed framing (owner 2026-07-12: "الفريم كله كأنه زوم مقصقص") — hermetic.

MEASURED root: the 'cover' default center-cropped every landscape real photo to a 37-42%
sliver (NTI's own photos), so every Veo seed and Ken Burns frame inherited a cropped,
zoomed-in world. New 'auto' default: portrait-ish -> cover (loss <= ~30%); landscape ->
OUTPAINT to 9:16 (real photo preserved), degrading to blur-contain (whole photo visible)."""
from __future__ import annotations

import io

from PIL import Image

import reel.video_provider as vp


def _jpg(w: int, h: int) -> bytes:
    """Solid green with a RED left edge and BLUE right edge — crop detectors."""
    img = Image.new("RGB", (w, h), (0, 160, 0))
    for x in range(6):
        for y in range(h):
            img.putpixel((x, y), (220, 0, 0))
            img.putpixel((w - 1 - x, y), (0, 0, 220))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _colors(data: bytes) -> set:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    hits = set()
    for x in range(img.width):
        r, g, b = img.getpixel((x, img.height // 2))
        if r > 140 and g < 90:
            hits.add("red")
        if b > 140 and g < 90:
            hits.add("blue")
    return hits


def test_landscape_keeps_the_whole_scene_via_blur_contain(monkeypatch):
    monkeypatch.delenv("REEL_SEED_FILL", raising=False)
    monkeypatch.setattr(vp, "_outpaint_seed", lambda d, w, h: None)   # no creds -> fallback
    out, mime = vp._to_vertical_seed(_jpg(800, 600))                  # ratio 1.33 (NTI class)
    img = Image.open(io.BytesIO(out))
    assert (img.width, img.height) == (768, 1366)
    # BOTH edges survive — the old cover default would have kept a 42% middle sliver
    assert _colors(out) == {"red", "blue"}


def test_landscape_prefers_real_outpaint_when_available(monkeypatch):
    monkeypatch.delenv("REEL_SEED_FILL", raising=False)
    marker = io.BytesIO()
    Image.new("RGB", (768, 1366), (200, 0, 200)).save(marker, format="JPEG")
    monkeypatch.setattr(vp, "_outpaint_seed", lambda d, w, h: marker.getvalue())
    out, _ = vp._to_vertical_seed(_jpg(800, 600))
    r, g, b = Image.open(io.BytesIO(out)).getpixel((384, 683))
    assert r > 150 and b > 150                                        # the outpainted canvas won


def test_portrait_still_covers_sharp(monkeypatch):
    monkeypatch.delenv("REEL_SEED_FILL", raising=False)
    monkeypatch.setattr(vp, "_outpaint_seed",
                        lambda d, w, h: (_ for _ in ()).throw(AssertionError("no outpaint")))
    out, _ = vp._to_vertical_seed(_jpg(600, 800))                     # ratio 0.75 -> cover
    img = Image.open(io.BytesIO(out))
    assert (img.width, img.height) == (768, 1366)
    r, g, b = img.getpixel((img.width // 2, 10))                      # top row is IMAGE, not a
    assert g > 120                                                    # dimmed blur band


def test_explicit_cover_override_still_wins(monkeypatch):
    monkeypatch.setenv("REEL_SEED_FILL", "cover")
    out, _ = vp._to_vertical_seed(_jpg(800, 600))
    assert _colors(out) == set()                                      # explicit crop: edges gone