"""Measure the exact exported artwork and capture 390px review PNGs."""
import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

from poster.campaign_package import layout_poster, poster_html
from tools.check_local_poster_preview import luminance


FIELDS = ".brand, h1, .item-name, .item-detail, .illustration-note, .message, .cta"


def measure(directory):
    report = json.loads((directory / "campaign.json").read_text())
    package = report["proposal"]["package"]
    results = {}
    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        for size, saved in report["poster_measurements"].items():
            width, height = saved["width"], saved["height"]
            png = directory / f"poster-{size}.png"
            assert hashlib.sha256(png.read_bytes()).hexdigest() == saved["sha256"]
            actual = np.asarray(Image.open(png).convert("RGB"), dtype=float)
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            external = []
            page.route("**/*", lambda route: (external.append(route.request.url), route.abort()))
            page.set_content(poster_html(package, width, height), wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            boxes = layout_poster(page, width, height)
            reference = np.asarray(Image.open(io.BytesIO(page.screenshot())).convert("RGB"), dtype=float)
            assert np.array_equal(actual, reference)
            fields = page.locator(FIELDS).evaluate_all(r"""elements => elements.map(e => {
                const css = getComputedStyle(e), b = e.getBoundingClientRect();
                return {field:e.className || e.tagName, text:e.innerText, font:parseFloat(css.fontSize),
                        color:css.color.match(/\d+/g).map(Number).slice(0,3), dir:css.direction,
                        box:[b.left,b.top,b.right,b.bottom].map(Math.round)};
            })""")
            # Hiding the text with transparent ink preserves grid dimensions and the CTA fill.
            page.add_style_tag(content=f":is({FIELDS}) {{color:transparent!important;}}")
            underlay = np.asarray(Image.open(io.BytesIO(page.screenshot())).convert("RGB"), dtype=float)
            for field in fields:
                left, top, right, bottom = field["box"]
                crop = actual[top:bottom, left:right]
                bg = underlay[top:bottom, left:right]
                pixels = (np.max(abs(crop - field["color"]), axis=2) < 10) & (np.max(abs(crop - bg), axis=2) > 20)
                assert pixels.sum() >= 100, field
                ink_l, bg_l = luminance(crop[pixels]), luminance(bg[pixels])
                field["minimum_interior_contrast"] = round(float(((np.maximum(ink_l, bg_l) + .05) /
                                                                    (np.minimum(ink_l, bg_l) + .05)).min()), 2)
                field["390px_font"] = round(field["font"] * 390 / width, 2)
                assert field["minimum_interior_contrast"] >= 4.5, field
            assert all(field["dir"] == "rtl" for field in fields if field["field"] != "brand")
            assert not external
            with Image.open(png) as img:
                img.resize((390, round(height * 390 / width)), Image.Resampling.LANCZOS).save(
                    directory / f"poster-{size}-390.png")
            results[size] = {"exact_raster_match": True, "geometry": boxes, "text": fields}
            page.close()
    (directory / "raster-checks.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    measure(parser.parse_args().directory)
