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
# Reuse the poster's PURE color helpers so the reel's accent matches the poster's
# (vivid, from the real palette). No coupling to PosterBrief — these take rgb/hex.
from poster.template import (
    _hex_to_rgb, _luminance, _saturation, _legible_on_dark, _readable_on,
)

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
    try:
        from scraper.url_utils import is_safe_public_url
        if not is_safe_public_url(url):
            return None
        from poster.template import _open_image_url
        data = _open_image_url(url, timeout=12).read()
        if not data:
            return None
        # SVG is allowed: Chromium renders it, and an <img>-referenced SVG runs in
        # secure static mode (no scripting). Recovers SVG-only brand logos.
        mime = "image/png"
        if low.endswith(".svg"):
            mime = "image/svg+xml"
        else:
            for ext, m in ((".jpg", "image/jpeg"), (".jpeg", "image/jpeg"),
                           (".webp", "image/webp"), (".png", "image/png")):
                if ext in low:
                    mime = m
                    break
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        return None


def _accent(storyboard: Storyboard) -> str:
    """The brand accent: the MOST SATURATED palette color with enough luminance to read
    on the dark lower scrim (vivid, not a muted tan) — mirrors the poster's `_brand_accent`
    over `[primary_color] + palette_hex`. White only if the palette is empty."""
    pal = [
        str(c) for c in ([storyboard.primary_color] + list(storyboard.palette_hex or []))
        if c and str(c).startswith("#")
    ]
    legible = [c for c in pal if _luminance(_hex_to_rgb(c)) >= 0.16]
    cand = legible or pal
    if cand:
        return max(cand, key=lambda c: _saturation(_hex_to_rgb(c)))
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


def _highlight_last_word(headline: str) -> str:
    """Escape the headline and wrap its LAST token in the accent span (one accent word —
    the editorial 'pop'). Verbatim text, CSS-only emphasis (zero-hallucination)."""
    words = _esc(headline).split(" ")
    if len(words) > 1:
        return " ".join(words[:-1]) + f' <span class="hl">{words[-1]}</span>'
    return f'<span class="hl">{words[0]}</span>' if words and words[0] else ""


def _scene_html(scene: ReelScene, storyboard: Storyboard, width: int, height: int,
                logo_uri: Optional[str]) -> str:
    """Transparent text-layer HTML for one scene — a bottom-anchored, safe-zone caption
    block (strong scrim, hero typography, one brand-accent word) instead of plain white
    text floating over the subject."""
    rtl = storyboard.primary_dir == "rtl"
    dir_attr = "rtl" if rtl else "ltr"
    accent = _accent(storyboard)                       # vivid, from the real palette
    accent_rgb = _hex_to_rgb(accent)
    accent_on_dark = _legible_on_dark(accent_rgb)      # accent text/rule on the dark scrim
    chip_text = _readable_on(accent_rgb)               # text INSIDE the accent CTA chip

    short = len((scene.headline or "").split()) <= 3
    head_px = round(width * (0.107 if short else 0.085))
    sub_px = round(width * 0.0425)
    cta_px = round(width * 0.046)
    logo_h = round(width * 0.11)
    edge = "flex-end" if rtl else "flex-start"         # ragged edge falls toward center
    shadow = "0 1px 2px rgba(0,0,0,.95), 0 2px 8px rgba(0,0,0,.7)"

    show_logo = bool(logo_uri) and scene.kind in ("intro", "outro", "contact")
    logo_pos = "right:56px" if rtl else "left:56px"
    logo_html = (f'<div class="logo" style="{logo_pos}"><img src="{logo_uri}"></div>'
                 if show_logo else "")

    blocks: list[str] = []
    if scene.headline:
        blocks.append('<div class="rule"></div>')
        blocks.append(f'<div class="headline">{_highlight_last_word(scene.headline)}</div>')
    if scene.sublines:
        items = "".join(f'<div class="sub-item">{_atom(s)}</div>' for s in scene.sublines)
        blocks.append(f'<div class="sub">{items}</div>')
    if scene.cta_text:
        blocks.append(f'<div class="cta-wrap"><span class="cta">{_esc(scene.cta_text)}</span></div>')

    return f"""<!doctype html><html dir="{dir_attr}" lang="ar"><head><meta charset="utf-8">
{_FONTS_LINK}
<style>
  html,body{{margin:0;padding:0;width:{width}px;height:{height}px;background:transparent;}}
  .stage{{position:relative;width:{width}px;height:{height}px;
    font-family:'Space Grotesk','Cairo',system-ui,sans-serif;color:#fff;overflow:hidden;
    --accent:{accent_on_dark};}}
  .lower{{position:absolute;left:0;right:0;bottom:0;padding:0 64px 300px;box-sizing:border-box;
    display:flex;flex-direction:column;align-items:{edge};text-align:start;
    background:linear-gradient(to top,
      rgba(8,12,18,.90) 0%, rgba(8,12,18,.68) 22%, rgba(8,12,18,.30) 45%, rgba(8,12,18,0) 64%);}}
  .lower>*{{unicode-bidi:plaintext;}}
  .rule{{height:6px;width:84px;background:var(--accent);border-radius:3px;margin-bottom:22px;}}
  .headline{{font-family:'Oswald','Cairo',system-ui,sans-serif;font-weight:700;
    font-size:{head_px}px;line-height:1.04;letter-spacing:-0.5px;text-transform:uppercase;
    max-width:80%;text-wrap:balance;text-shadow:{shadow};
    -webkit-text-stroke:0.5px rgba(0,0,0,.35);}}
  .headline .hl{{color:var(--accent);}}
  .sub{{font-family:'Inter','Cairo',system-ui,sans-serif;font-weight:600;
    font-size:{sub_px}px;line-height:1.45;margin-top:20px;max-width:82%;text-shadow:{shadow};}}
  .sub-item{{margin:0.16em 0;}}
  .cta-wrap{{margin-top:30px;}}
  .cta{{display:inline-block;font-weight:700;font-size:{cta_px}px;
    background:{accent};color:{chip_text};padding:0.42em 0.95em;border-radius:14px;
    letter-spacing:0.3px;box-shadow:0 6px 22px rgba(0,0,0,.42);}}
  .logo{{position:absolute;top:60px;}}
  .logo img{{height:{logo_h}px;max-width:42%;object-fit:contain;
    filter:drop-shadow(0 2px 12px rgba(0,0,0,.55));}}
</style></head>
<body><div class="stage">{logo_html}<div class="lower">{''.join(blocks)}</div></div></body></html>"""


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
