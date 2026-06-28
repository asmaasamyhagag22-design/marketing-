"""Hermetic tests for the Imagen EDIT provider (no live Vertex calls — the live edit_image
capability is verified out-of-CI by the 2026-06-27 probe). Covers the pure mask geometry,
SSRF-guarded fetch, and the no-reference / unfetchable-base guard paths."""
import io

import pytest
from PIL import Image

from poster.imagen_edit_provider import (
    ImagenEditProvider,
    build_outpaint_canvas_and_mask,
    upscale_to_file,
    _fetch_bytes,
)


def _png(w, h, color=(200, 30, 30)) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "PNG")
    return b.getvalue()


def test_outpaint_mask_geometry():
    """Canvas == target; real photo centered; mask BLACK over the photo (keep) and WHITE in
    the outpaint border (fill)."""
    from PIL import Image
    base = _png(200, 100)
    canvas, mask, (ox, oy, nw, nh) = build_outpaint_canvas_and_mask(base, target=(400, 500), coverage=0.5)

    cimg = Image.open(io.BytesIO(canvas))
    mimg = Image.open(io.BytesIO(mask)).convert("L")
    assert cimg.size == (400, 500)
    assert mimg.size == (400, 500)
    # photo region is inside the canvas and centered
    assert 0 < ox and 0 < oy and ox + nw <= 400 and oy + nh <= 500
    # center pixel = over the photo => keep => BLACK(0); corner = border => fill => WHITE(255)
    assert mimg.getpixel((200, 250)) == 0
    assert mimg.getpixel((2, 2)) == 255


def test_outpaint_coverage_scales_photo():
    """Higher coverage => the kept photo occupies more of the canvas."""
    base = _png(100, 100)
    _, _, (_, _, nw_small, _) = build_outpaint_canvas_and_mask(base, target=(600, 600), coverage=0.4)
    _, _, (_, _, nw_big, _) = build_outpaint_canvas_and_mask(base, target=(600, 600), coverage=0.8)
    assert nw_big > nw_small


def test_fetch_bytes_ssrf_and_scheme_guard():
    assert _fetch_bytes("http://127.0.0.1/x.png") is None      # loopback blocked
    assert _fetch_bytes("ftp://example.com/x.png") is None     # non-http scheme
    assert _fetch_bytes("not-a-url") is None
    assert _fetch_bytes(12345) is None                          # type guard


def test_image_accepts_bytes_and_rejects_unfetchable():
    prov = ImagenEditProvider(project="dummy", fetch=lambda u: None)  # fetch always fails
    assert prov._image(_png(40, 40)) is not None                 # raw bytes -> Image
    assert prov._image("https://example.com/blocked.png") is None  # injected fetch -> None


def test_style_raises_without_usable_reference_no_network():
    """All refs unfetchable -> raises BEFORE any client/network call (hermetic)."""
    prov = ImagenEditProvider(project="dummy", fetch=lambda u: None)
    with pytest.raises(RuntimeError, match="no usable style reference"):
        prov.style("a scene", ["https://example.com/a.png", "https://example.com/b.png"])


def test_outpaint_raises_when_base_unfetchable_no_network():
    prov = ImagenEditProvider(project="dummy", fetch=lambda u: None)
    with pytest.raises(RuntimeError, match="could not load base image"):
        prov.outpaint("https://example.com/missing.png")


def test_upscale_to_file_safe_noop_on_unreadable(tmp_path):
    missing = str(tmp_path / "nope.png")
    assert upscale_to_file(missing) == missing          # unreadable -> returns original, no raise


def test_upscale_to_file_noop_without_project(tmp_path, monkeypatch):
    p = tmp_path / "x.png"
    Image.new("RGB", (64, 64), (10, 20, 30)).save(p)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    assert upscale_to_file(str(p), project="") == str(p)  # no project -> no network, no-op
