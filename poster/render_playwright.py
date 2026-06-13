"""HTML/CSS -> PNG via headless Chromium (Playwright). No Pillow.

Renders the full poster (background + overlaid text zones) by loading an HTML
string in Chromium and screenshotting a fixed poster canvas. device_scale_factor
gives crisp typography (2x => 2160x2700 pixels for a 1080x1350 CSS canvas).
"""
from __future__ import annotations

from pathlib import Path

POSTER_W = 1080
POSTER_H = 1350


def render_html_to_png(
    html: str,
    out_path: str | Path,
    *,
    width: int = POSTER_W,
    height: int = POSTER_H,
    scale: int = 2,
) -> Path:
    from playwright.sync_api import sync_playwright

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=scale,
            )
            # Background is inlined as a data URI, but Google Fonts load over the
            # network — networkidle covers their requests, and document.fonts.ready
            # guarantees the faces are applied before we screenshot (else the first
            # paint can fall back to a system font).
            page.set_content(html, wait_until="networkidle")
            try:
                page.evaluate("async () => { await document.fonts.ready; }")
            except Exception:
                pass
            page.screenshot(
                path=str(out_path),
                clip={"x": 0, "y": 0, "width": width, "height": height},
            )
        finally:
            browser.close()

    return out_path
