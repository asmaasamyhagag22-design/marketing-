"""Render the reel's TEXT layer as transparent PNGs via headless Chromium.

This reuses the poster's proven approach: the browser shapes Arabic correctly
(connected, RTL) where the bundled ffmpeg/libass does NOT. We render one
transparent 1080x1920 PNG per scene (logo + verbatim text, brand-styled) and the
compositor overlays each on its scene clip with a fade.

ZERO HALLUCINATION: every word comes verbatim from the storyboard (which came from
the profile). The logo is the brand's own scraped logo, fetched SSRF-guarded.
"""
from __future__ import annotations

import base64
import html as _html
import re
from pathlib import Path
from typing import Optional

from .schemas import ReelScene, Storyboard

# Google Fonts: Cairo covers Arabic (so RTL text shapes), Space Grotesk + Inter
# give a modern Latin display/body. Arabic chars fall through to Cairo automatically.
_FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Cairo:wght@400;600;700;900&'
    'family=Oswald:wght@500;600;700&'
    'family=Space+Grotesk:wght@500;700&'
    'family=Inter:wght@400;600&display=swap" rel="stylesheet">'
)


def _logo_data_uri(url: Optional[str]) -> Optional[str]:
    """SSRF-guarded fetch of the brand logo -> data URI for inlining. None on any
    failure or non-raster source (the reel renders fine without it)."""
    if not url or url.startswith("text-wordmark:"):
        return None
    if url.startswith("data:"):
        return url
    low = url.lower().split("?")[0]
    if low.endswith(".svg"):
        return None
    try:
        from scraper.url_utils import is_safe_public_url
        if not is_safe_public_url(url):
            return None
        from poster.template import _open_image_url
        data = _open_image_url(url, timeout=12).read()
        if not data:
            return None
        mime = "image/png"
        for ext, m in ((".jpg", "image/jpeg"), (".jpeg", "image/jpeg"),
                       (".webp", "image/webp"), (".png", "image/png")):
            if ext in low:
                mime = m
                break
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        return None


def _accent(storyboard: Storyboard) -> str:
    """A legible (non-dark) accent for the CTA; white if none qualifies."""
    for hexc in (storyboard.palette_hex or []):
        c = (hexc or "").lstrip("#")
        if len(c) == 6:
            try:
                r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
            except ValueError:
                continue
            if r + g + b > 300:
                return f"#{c.upper()}"
    return "#FFFFFF"


def _esc(text: str) -> str:
    return _html.escape((text or "").strip())


# Phone / email / URL: inherently left-to-right. In an RTL reel these get
# bidi-mangled (digits/segments reorder) unless isolated as LTR.
_LTR_ATOM = re.compile(
    r"^\s*(\+?\d[\d\s\-()./]{4,}\d|[^\s@]+@[^\s@]+\.[^\s@]+|https?://\S+|www\.\S+)\s*$"
)


def _atom(text: str) -> str:
    """Escape, and isolate phone/email/URL atoms as LTR so they render correctly
    inside an RTL reel."""
    esc = _esc(text)
    if text and _LTR_ATOM.match(text):
        return f'<span dir="ltr" style="unicode-bidi:isolate;display:inline-block">{esc}</span>'
    return esc


def _scene_html(scene: ReelScene, storyboard: Storyboard, width: int, height: int,
                logo_uri: Optional[str]) -> str:
    """Transparent text-layer HTML for one scene."""
    dir_attr = storyboard.primary_dir  # 'rtl' | 'ltr'
    accent = _accent(storyboard)
    head_px = round(width * 0.086)
    sub_px = round(width * 0.047)
    cta_px = round(width * 0.055)
    logo_h = round(width * 0.12)
    shadow = "0 4px 26px rgba(0,0,0,.62), 0 1px 3px rgba(0,0,0,.9)"

    show_logo = bool(logo_uri) and scene.kind in ("intro", "outro", "contact")
    logo_html = (
        f'<div class="logo"><img src="{logo_uri}"></div>' if show_logo else ""
    )

    blocks: list[str] = []
    if scene.headline:
        top = "41%" if scene.kind == "intro" else "45%"
        blocks.append(
            f'<div class="row headline" style="top:{top}">{_esc(scene.headline)}</div>'
        )
    if scene.sublines:
        items = "".join(f'<div class="sub-item">{_atom(s)}</div>' for s in scene.sublines)
        blocks.append(f'<div class="row sub" style="top:47%">{items}</div>')
    if scene.cta_text:
        blocks.append(f'<div class="row cta" style="top:63%">{_esc(scene.cta_text)}</div>')

    return f"""<!doctype html><html dir="{dir_attr}" lang="ar"><head><meta charset="utf-8">
{_FONTS_LINK}
<style>
  html,body{{margin:0;padding:0;width:{width}px;height:{height}px;background:transparent;}}
  .stage{{position:relative;width:{width}px;height:{height}px;
    font-family:'Space Grotesk','Cairo',system-ui,sans-serif;color:#fff;overflow:hidden;}}
  .scrim{{position:absolute;inset:0;
    background:radial-gradient(64% 44% at 50% 49%, rgba(0,0,0,.42), rgba(0,0,0,0) 72%);}}
  .row{{position:absolute;left:0;right:0;text-align:center;
    padding:0 7%;box-sizing:border-box;transform:translateY(-50%);}}
  .headline{{font-family:'Oswald','Cairo',system-ui,sans-serif;font-weight:700;
    font-size:{head_px}px;line-height:1.1;letter-spacing:0.5px;text-transform:uppercase;
    text-shadow:{shadow};}}
  .sub{{font-family:'Inter','Cairo',system-ui,sans-serif;font-weight:600;
    font-size:{sub_px}px;line-height:1.5;text-shadow:{shadow};}}
  .sub-item{{margin:0.34em 0;}}
  .cta{{font-weight:700;font-size:{cta_px}px;color:{accent};text-shadow:{shadow};letter-spacing:0.3px;}}
  .logo{{position:absolute;top:6.5%;left:0;right:0;text-align:center;}}
  .logo img{{height:{logo_h}px;max-width:60%;object-fit:contain;
    filter:drop-shadow(0 2px 12px rgba(0,0,0,.6));}}
</style></head>
<body><div class="stage"><div class="scrim"></div>{logo_html}{''.join(blocks)}</div></body></html>"""


def render_text_layers(
    storyboard: Storyboard,
    *,
    width: int,
    height: int,
    out_dir: Path,
    include_logo: bool = True,
) -> list[Path]:
    """Render one transparent PNG per scene (single browser session). Returns the
    paths in scene order."""
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    logo_uri = _logo_data_uri(storyboard.logo_url) if include_logo else None
    paths: list[Path] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for i, scene in enumerate(storyboard.scenes):
                page = browser.new_page(
                    viewport={"width": width, "height": height}, device_scale_factor=1,
                )
                page.set_content(
                    _scene_html(scene, storyboard, width, height, logo_uri),
                    wait_until="networkidle",
                )
                try:
                    page.evaluate("async () => { await document.fonts.ready; }")
                except Exception:
                    pass
                out = out_dir / f"text{i}.png"
                page.screenshot(
                    path=str(out), omit_background=True,
                    clip={"x": 0, "y": 0, "width": width, "height": height},
                )
                page.close()
                paths.append(out)
        finally:
            browser.close()

    return paths
