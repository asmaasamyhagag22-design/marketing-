"""Brand-tinted film grade as a Hald CLUT (the owner's idea #ب).

Bake the film grade (+ a subtle push toward the brand-DNA hue) into ONE Hald CLUT image via
ffmpeg's `haldclutsrc`, then apply it to EVERY clip with the `haldclut` filter — fed as a normal
ffmpeg INPUT, so there is no fragile in-filtergraph file path to escape on Windows. One identical
colour transform across all shots = true film cohesion. The caller falls back to the inline
eq+curves grade if CLUT generation fails. Never raises.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from reel.ffmpeg_tools import run_ffmpeg

# Base film grade baked into the CLUT: a GENTLE filmic curve + a small contrast lift. Kept
# colour-NEUTRAL (no saturation pump, no brand-hue push) so it never makes colours clash with
# the footage — the owner saw "بايظة" colours when a purple tint hit green WE footage.
_BASE = "curves=m='0/0.02 0.5/0.5 1/0.98',eq=contrast=1.04:saturation=1.0:gamma=0.99"


def _brand_tint(palette: Optional[list[str]]) -> str:
    """A subtle midtone push toward the brand's dominant hue so every clip shares its mood."""
    try:
        from poster.template import _hex_to_rgb
        hexes = [c for c in (palette or []) if isinstance(c, str) and c.startswith("#")]
        if not hexes:
            return ""
        r, g, b = _hex_to_rgb(hexes[0])
        mean = (r + g + b) / 3.0 or 1.0

        def s(v: float) -> float:                       # gentle mood, not a heavy colour cast
            return max(-0.06, min(0.06, (v - mean) / 255.0 * 0.35))

        return f",colorbalance=rm={s(r):.3f}:gm={s(g):.3f}:bm={s(b):.3f}"
    except Exception:
        return ""


def build_brand_clut(out_png: str | Path, palette: Optional[list[str]] = None,
                     level: int = 6) -> Optional[Path]:
    """Generate the brand film-grade Hald CLUT. Returns the path, or None (caller uses the inline
    grade). `level=6` → a 36^3 lattice (216x216 px) — plenty for a tonal/tint grade, fast to bake."""
    out_png = Path(out_png)
    chain = _BASE   # colour-neutral; brand identity comes from the footage + logo, not a tint
    try:
        run_ffmpeg(["-f", "lavfi", "-i", f"haldclutsrc=level={level}",
                    "-vf", chain, "-frames:v", "1", str(out_png)])
    except Exception:
        return None
    return out_png if out_png.exists() else None
