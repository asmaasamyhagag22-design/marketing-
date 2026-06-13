"""Build the poster HTML/CSS from a PosterBrief + a background image.

Design rules enforced here (per the redesign constraints):
- EVIDENCE-ONLY at the template layer: a missing/empty field is OMITTED, never
  fabricated. (Note: build_poster_brief still injects some fallback copy upstream;
  stripping that is the next, separate step.)
- Headline is rendered exactly ONCE.
- Typographic register is VARIED — natural-case brand + headline (serif), an
  uppercase letter-spaced kicker as a single accent, sans-serif body/chips. No
  global uppercasing.
- The background is a real visual; we apply a legibility scrim ONLY behind the
  lower text block, not a full-image darken.
"""
from __future__ import annotations

import base64
import html as _html
import re
from pathlib import Path
from typing import Optional

# Arabic + Hebrew + Arabic presentation forms — used to right-align RTL copy.
_RTL_RE = re.compile(
    r"[֐-׿؀-ۿ܀-ݏݐ-ݿࢠ-ࣿיִ-﷿ﹰ-﻿]"
)


def _is_rtl(text) -> bool:
    return bool(_RTL_RE.search(str(text or "")))

from poster.schemas import PosterBrief


def _data_uri(image_path) -> str:
    raw = Path(image_path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def _open_image_url(url: str, timeout: int):
    """Open an image URL with a verified SSL context (certifi when available),
    falling back to an UNVERIFIED context on a cert-chain failure.

    Why the fallback is acceptable HERE: the target is already SSRF-guarded to a
    public host, this is a passive IMAGE fetch with no credentials sent, and many
    real sites (e.g. nti.sci.eg) ship an INCOMPLETE cert chain — browsers repair it
    via AIA fetching but Python's urllib does not, so a strict fetch drops the real
    logo to a text wordmark. The worst case of a MITM swapping a logo image is
    cosmetic, not a data/credential risk.
    """
    import ssl
    from urllib.request import Request, urlopen
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (PosterStudio)"})
    try:
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl.create_default_context()
        return urlopen(req, timeout=timeout, context=ctx)
    except Exception as exc:                       # noqa: BLE001
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            return urlopen(req, timeout=timeout, context=ssl._create_unverified_context())
        raise


def _remote_image_data_uri(url: str, timeout: int = 8) -> Optional[str]:
    """Fetch a remote raster logo and inline it as a data URI (deterministic
    render, no broken <img>). Returns None on any failure or for SVG.

    SSRF guard: the logo URL comes from user-supplied profile data, so we only
    fetch public http(s) hosts (no localhost/internal/metadata addresses).
    """
    from scraper.url_utils import is_safe_public_url
    if not is_safe_public_url(url):
        return None
    try:
        with _open_image_url(url, timeout) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            data = r.read(4_000_000)
        low = url.lower()
        if not data or "svg" in ctype or low.endswith(".svg"):
            return None
        mime = "image/png"
        if "jpeg" in ctype or low.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif "webp" in ctype or low.endswith(".webp"):
            mime = "image/webp"
        elif "gif" in ctype or low.endswith(".gif"):
            mime = "image/gif"
        return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    except Exception:
        return None


def _esc(value) -> str:
    return _html.escape(str(value)) if value not in (None, "") else ""


def _accent(brief: PosterBrief) -> str:
    for color in [brief.primary_color, *(brief.palette_hex or [])]:
        if color and str(color).startswith("#"):
            return str(color)
    return "#c79a4b"


# --- contrast-aware color helpers (keep brand color, guarantee legibility) ---

def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    h = str(value).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (199, 154, 75)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def _luminance(rgb) -> float:
    def ch(v: float) -> float:
        x = v / 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _mix(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def _readable_on(rgb) -> str:
    """Near-black or white text — whichever contrasts better with the given bg."""
    return "#0b0f16" if _luminance(rgb) > 0.45 else "#ffffff"


def _legible_on_dark(rgb) -> str:
    """Lighten a too-dark accent so it reads on the dark lower scrim; else keep it."""
    return _to_hex(rgb) if _luminance(rgb) >= 0.40 else _to_hex(_mix(rgb, (255, 255, 255), 0.62))


# Fonts we never request from Google Fonts (system/generic/private). Any OTHER
# named family is requested best-effort; if it isn't a real Google Font the link
# simply no-ops and the curated default below applies.
_GENERIC_FONTS = {
    "system-ui", "-apple-system", "blinkmacsystemfont", "ui-sans-serif",
    "ui-serif", "ui-monospace", "sans-serif", "serif", "monospace",
    "inherit", "initial", "unset", "segoe ui", "arial", "helvetica",
    "times new roman", "tahoma", "verdana", "georgia", "roboto",
}


def _is_loadable_font(name: Optional[str]) -> bool:
    if not name:
        return False
    n = str(name).strip().strip("'\"")
    if n.lower() in _GENERIC_FONTS:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9 ]{2,40}", n))


def _gf_param(name: str) -> str:
    return str(name).strip().strip("'\"").replace(" ", "+")


def _fonts_head_and_stacks(brief: PosterBrief, rtl: bool) -> tuple[str, str, str]:
    """(head_links, font_head_stack, font_body_stack).

    Always loads a curated MODERN default pairing (Space Grotesk + Inter + Cairo)
    so the poster never falls back to a boring system serif. ALSO best-effort loads
    the brand's OWN fonts on a SEPARATE <link> — kept separate so an invalid brand
    family (e.g. a private 'myfont2') can 400 without taking the defaults down.
    The brand font leads each stack, so it's used when it actually loads.
    """
    head = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Space+Grotesk:wght@500;700&family=Inter:wght@400;600&'
        'family=Cairo:wght@500;700;800&display=swap">'
    )
    bh = str(brief.heading_font or "").strip().strip("'\"")
    bb = str(brief.body_font or "").strip().strip("'\"")
    fams = []
    if _is_loadable_font(bh):
        fams.append(bh)
    if _is_loadable_font(bb) and bb.lower() != bh.lower():
        fams.append(bb)
    if fams:
        q = "&".join(f"family={_gf_param(f)}:wght@400;700" for f in fams)
        head += f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{q}&display=swap">'

    head_brand = f"'{bh}', " if _is_loadable_font(bh) else ""
    body_brand = f"'{bb}', " if _is_loadable_font(bb) else ""
    if rtl:
        font_head = f"{head_brand}'Cairo', 'Space Grotesk', Georgia, serif"
        font_body = f"{body_brand}'Cairo', 'Inter', Arial, sans-serif"
    else:
        font_head = f"{head_brand}'Space Grotesk', 'Cairo', Georgia, serif"
        font_body = f"{body_brand}'Inter', 'Cairo', Arial, sans-serif"
    return head, font_head, font_body


def _headline_block(brief: PosterBrief, rtl: bool) -> str:
    """A DESIGNED headline, not a flat line.

    Short headlines become a STACKED HERO — each word on its own line, auto-sized
    so the longest word fills the text column, with the final word in the accent
    color (the 'BUSINESS / IDEAS' treatment). Longer headlines stay a clean block.

    ZERO-HALLUCINATION: the words are the verbatim headline, only RE-STYLED — none
    added, removed, reordered, or reworded. (Uppercasing is applied to Latin text
    only via CSS; the underlying string is unchanged.)
    """
    text = (brief.headline or "").strip()
    words = text.split()
    longest = max((len(w) for w in words), default=0)
    is_hero = 1 <= len(words) <= 4 and 0 < longest <= 18
    if not is_hero:
        return f'<h1 class="headline">{_esc(text)}</h1>'

    # Auto-fit: the longest word should span most of the ~920px text column, so the
    # hero fills the width dramatically regardless of word length.
    size = max(46, min(118, int(920 / (longest * 0.60))))
    upper_cls = "" if rtl else " upper"        # Arabic/Hebrew have no letter case
    spans = []
    for i, w in enumerate(words):
        accent = " accent" if (i == len(words) - 1 and len(words) > 1) else ""
        spans.append(f'<span class="hw{accent}">{_esc(w)}</span>')
    return (
        f'<div class="hero-headline{upper_cls}" style="font-size:{size}px">'
        f'{"".join(spans)}</div>'
    )


def render_poster_html(
    brief: PosterBrief,
    background_path: Optional[str] = None,
    density: str = "minimal",
) -> str:
    accent = _accent(brief)
    accent_rgb = _hex_to_rgb(accent)
    kicker_color = _legible_on_dark(accent_rgb)   # readable on the dark scrim
    cta_bg = accent                               # keep the brand color on the button
    cta_text = _readable_on(accent_rgb)           # white on a dark brand color, dark on a light one

    if background_path:
        bg_layer = f"url('{_data_uri(background_path)}') center/cover no-repeat"
    else:
        # --no-image path: a brand-palette gradient, no Pillow involved.
        second = (brief.palette_hex or ["#0e131b"])[-1]
        bg_layer = f"linear-gradient(135deg, {accent} 0%, {second} 100%)"

    # --- evidence-only blocks: built only when the field exists ---
    kicker_html = ""
    if brief.category:
        kicker_html = f'<div class="kicker">{_esc(brief.category.replace("_", " "))}</div>'

    sub_html = f'<p class="sub">{_esc(brief.subheadline)}</p>' if brief.subheadline else ""

    offerings_html = ""
    if brief.offerings:
        items = "".join(f"<li>{_esc(o)}</li>" for o in brief.offerings[:3] if o)
        if items:
            offerings_html = f'<ul class="offerings">{items}</ul>'

    cta_html = ""
    if brief.cta_text:
        url = _esc(brief.cta_url)
        # dir="ltr" so URLs/emails aren't reordered by an RTL (Arabic) container.
        url_span = f'<span class="cta-url" dir="ltr">{url}</span>' if url else ""
        cta_html = (
            f'<div class="cta"><span class="cta-text">{_esc(brief.cta_text)}</span>{url_span}</div>'
        )

    contact_html = f'<p class="contact" dir="ltr">{_esc(brief.contact_line)}</p>' if brief.contact_line else ""

    # Evidence-backed social profiles (platform labels; a PNG can't be clickable).
    social_html = ""
    if brief.social:
        labels = {
            "facebook": "Facebook", "instagram": "Instagram", "linkedin": "LinkedIn",
            "youtube": "YouTube", "tiktok": "TikTok", "twitter": "X", "x": "X",
            "whatsapp": "WhatsApp", "telegram": "Telegram", "snapchat": "Snapchat",
            "pinterest": "Pinterest",
        }
        row = " · ".join(
            _esc(labels.get((s.platform or "").lower(), (s.platform or "link").capitalize()))
            for s in brief.social[:6]
        )
        social_html = f'<p class="socials">{row}</p>'

    # Brand mark: a real logo image (inlined) on a light plate; else wordmark text.
    logo_src = None
    if brief.logo_url and brief.logo_url.startswith("data:image"):
        logo_src = brief.logo_url
    elif brief.logo_url and brief.logo_url.startswith(("http://", "https://")):
        logo_src = _remote_image_data_uri(brief.logo_url)
    # RTL: detect from the actual copy (Arabic headline/brand) -> right-align the
    # overlay and move the logo to the top-right.
    rtl = _is_rtl(brief.headline) or _is_rtl(brief.business_name)
    rtl_cls = " rtl" if rtl else ""
    dir_attr = "rtl" if rtl else "ltr"

    # Typography: the website's own fonts when loadable, else a curated modern
    # default — never the boring system serif.
    font_links, font_head, font_body = _fonts_head_and_stacks(brief, rtl)

    # A short accent rule above the headline — a small piece of brand-colored
    # flair so the lower block reads designed, not a flat slab of text.
    accent_rule_html = '<div class="accent-rule"></div>'

    if logo_src:
        brand_html = f'<img class="brand-logo{rtl_cls}" src="{logo_src}" alt="{_esc(brief.business_name)}">'
    else:
        brand_html = f'<div class="brand{rtl_cls}">{_esc(brief.business_name)}</div>'

    headline_html = f'<h1 class="headline">{_esc(brief.headline)}</h1>'
    if density == "minimal":
        # Ultra-minimal hero: accent rule + headline + one CTA (logo is the mark above).
        lower_inner = f"{accent_rule_html}\n      {headline_html}\n      {cta_html}"
    else:
        lower_inner = (
            f"{kicker_html}\n      {accent_rule_html}\n      {headline_html}\n      {sub_html}\n      "
            f"{offerings_html}\n      {cta_html}\n      {contact_html}\n      {social_html}"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">{font_links}<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:1080px; height:1350px; }}
  .canvas {{
    position:relative; width:1080px; height:1350px; overflow:hidden;
    background:#0e131b {bg_layer};
    font-family:{font_body}; color:#f5f3ef;
  }}
  .brand {{
    position:absolute; top:62px; left:80px; right:80px;
    font-family:{font_head}; font-size:32px; font-weight:700; letter-spacing:.01em; color:#ffffff;
    text-shadow:0 2px 10px rgba(0,0,0,.55);
  }}
  .brand-logo {{
    position:absolute; top:54px; left:80px; max-height:88px; max-width:360px;
    width:auto; object-fit:contain; background:rgba(255,255,255,.94);
    padding:12px 18px; border-radius:14px; box-shadow:0 4px 18px rgba(0,0,0,.35);
  }}
  /* RTL (Arabic/Hebrew): right-align text, move the logo to the top-right. */
  .brand.rtl {{ text-align:right; }}
  .brand-logo.rtl {{ left:auto; right:80px; }}
  .lower.rtl {{ direction:rtl; text-align:right; }}
  .lower {{
    position:absolute; left:0; right:0; bottom:0; padding:74px 80px 64px;
    background:linear-gradient(to top,
      rgba(8,12,18,.90) 0%, rgba(8,12,18,.76) 52%, rgba(8,12,18,0) 100%);
  }}
  /* brand-colored flair bar above the headline */
  .accent-rule {{
    width:68px; height:6px; border-radius:4px; margin:0 0 22px;
    background:{accent}; box-shadow:0 2px 12px {accent}66;
  }}
  .lower.rtl .accent-rule {{ margin-left:auto; }}
  .kicker {{
    font-family:{font_body}; font-size:18px; font-weight:700;
    letter-spacing:.24em; text-transform:uppercase; color:{kicker_color}; margin-bottom:16px;
  }}
  .headline {{
    font-family:{font_head}; font-size:67px; line-height:1.03; font-weight:700;
    letter-spacing:-.012em; margin-bottom:24px;
  }}
  .sub {{
    font-family:{font_body}; font-size:24px; line-height:1.42;
    color:#e6ecf2; margin-bottom:30px; max-width:780px;
  }}
  .offerings {{ list-style:none; display:flex; flex-wrap:wrap; gap:12px; margin-bottom:34px; }}
  .offerings li {{
    font-family:{font_body}; font-size:19px; padding:10px 18px;
    border:1px solid rgba(255,255,255,.42); border-radius:999px; color:#eef3f8;
  }}
  .cta {{
    display:inline-flex; align-items:baseline; gap:16px;
    background:{cta_bg}; color:{cta_text}; padding:18px 30px; border-radius:14px;
  }}
  .cta-text {{ font-family:{font_body}; font-weight:700; font-size:24px; }}
  .cta-url {{ font-family:{font_body}; font-size:18px; opacity:.82; }}
  .contact {{ font-family:{font_body}; font-size:18px; color:#cdd6df; margin-top:22px; }}
  .socials {{ font-family:{font_body}; font-size:18px; color:#aeb8c4; margin-top:12px; letter-spacing:.02em; }}
</style></head>
<body>
  <div class="canvas">
    {brand_html}
    <div class="lower{rtl_cls}" dir="{dir_attr}">
      {lower_inner}
    </div>
  </div>
</body></html>"""
