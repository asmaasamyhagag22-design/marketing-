"""Universal technical-quality gate for scraped content images.

WHY (measured, not guessed)
---------------------------
The reel animates a brand's scraped `content_images`. But a brand's "content images" are
frequently NOT usable photos: tiny category thumbnails (MEASURED on Orange Egypt: 298x175 /
221x130 px — upscaling those to a 1080x1920 reel = a blurry "dumb frame"), wide banners with
baked text, or near-blank product-on-white graphics. The vision curator judges CONTENT ("is
this on-brand?" — and an Orange banner IS on-brand) but NOT technical USABILITY. So garbage
gets animated. This gate is the missing deterministic, UNIVERSAL technical filter (size /
aspect / blankness) — no vertical logic, no brand-specific hacks.

CALIBRATION (measured across good- and bad-photo brands, before choosing thresholds)
-----------------------------------------------------------------------------------
    elkbabgi (real photos 960-2000px)  -> KEEP 12/12
    digilians (1000-1024px)            -> KEEP 4/5  (the 1 reject is a Facebook tracking pixel)
    Orange Egypt (298x175 thumbnails)  -> KEEP 0/12 (-> the reel routes to generated b-roll)
The dominant, well-separated signal is short-side resolution (Orange max 237px vs elkbabgi
min 800px); ratio/blankness are safety nets for a large-but-useless banner.

Pure/deterministic for `assess_photo`; `filter_usable_photos` fetches (SSRF-guarded, injectable)
and never raises.
"""
from __future__ import annotations

import io
from typing import Callable, Optional

# Thresholds — MEASURED/calibrated (see module docstring). Universal, not vertical.
_MIN_SHORT_SIDE = 500       # px: below this, upscaling to 1080x1920 visibly blurs
_MAX_RATIO = 2.6            # max long/short: above this it's a banner strip, not a photo
_MAX_WHITE_PCT = 88.0       # % near-white pixels: above this it's blank / product-on-white
_LUM_LO, _LUM_HI = 12.0, 244.0   # mean luminance: outside this it's near-black / near-white


def assess_photo(
    width: int, height: int,
    mean_lum: Optional[float] = None, white_pct: Optional[float] = None,
) -> tuple[bool, str]:
    """Pure: is this image a USABLE reel/poster background photo? -> (ok, reason).

    Only `width`/`height` are required (the dominant signal); `mean_lum`/`white_pct` are
    optional safety nets for a large-but-blank graphic."""
    if not width or not height or width <= 0 or height <= 0:
        return False, "no_dimensions"
    short = min(width, height)
    ratio = max(width, height) / short
    if short < _MIN_SHORT_SIDE:
        return False, f"too_small({short}px)"
    if ratio > _MAX_RATIO:
        return False, f"banner_ratio({ratio:.1f})"
    if white_pct is not None and white_pct > _MAX_WHITE_PCT:
        return False, f"near_blank({white_pct:.0f}%_white)"
    if mean_lum is not None and (mean_lum < _LUM_LO or mean_lum > _LUM_HI):
        return False, f"extreme_lum({mean_lum:.0f})"
    return True, "ok"


def measure_bytes(data: bytes) -> Optional[tuple[int, int, float, float]]:
    """(width, height, mean_lum, white_pct) from image bytes; None if undecodable.
    Luminance stats are taken from a tiny thumbnail so this is fast on large images."""
    if not data:
        return None
    try:
        from PIL import Image, ImageStat
        im = Image.open(io.BytesIO(data))
        im.load()
        w, h = im.size
        small = im.convert("L").resize((96, 96))
        mean = ImageStat.Stat(small).mean[0]
        px = list(small.getdata())
        white = sum(1 for v in px if v >= 238) / len(px) * 100.0
        return int(w), int(h), float(mean), float(white)
    except Exception:
        return None


def _default_fetch(url: str) -> Optional[bytes]:
    """SSRF-guarded http(s) fetch (same discipline as the poster/reel logo fetch)."""
    try:
        from scraper.url_utils import is_safe_public_url
        if not is_safe_public_url(url):
            return None
        import urllib.request
        hdr = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")}
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=15) as r:
            return r.read()
    except Exception:
        return None


def filter_usable_photos(
    urls, *, fetch: Optional[Callable[[str], Optional[bytes]]] = None, max_keep: int = 12,
) -> list[str]:
    """Keep only the URLs that resolve to USABLE photos (order preserved). UNIVERSAL, never
    raises. `fetch(url) -> bytes|None` is injectable (default: SSRF-guarded http) so tests stay
    hermetic. An undecodable / unreachable / failing-gate image is silently dropped."""
    fetch = fetch or _default_fetch
    out: list[str] = []
    for u in (urls or []):
        if not isinstance(u, str) or not u.startswith(("http://", "https://")):
            continue
        m = measure_bytes(fetch(u))
        if not m:
            continue
        ok, _why = assess_photo(*m)
        if ok:
            out.append(u)
        if len(out) >= max_keep:
            break
    return out
