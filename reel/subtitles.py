"""Build a libass (.ass) subtitle script that overlays the storyboard's VERBATIM
text on the global reel timeline.

libass (with libharfbuzz + libfribidi, both in the bundled ffmpeg) shapes Arabic
and resolves RTL bidi automatically — we just emit the verbatim text and libass
does the right thing. Text is white with a thick dark outline so it stays legible
over unpredictable Veo footage; the CTA uses the brand accent color.

PlayResX/Y are pinned to the 1080x1920 reference so libass scales text correctly
to ANY output resolution (a low-res preview and the full-res render look identical
in layout) — a lesson the poster's HTML overlay also relies on.
"""
from __future__ import annotations

from typing import Optional

from .from_profile import is_rtl
from .schemas import REEL_H, REEL_W, Storyboard


def _shape(text: str) -> str:
    """Pre-join Arabic into connected presentation forms.

    The bundled libass does RTL REORDERING (FriBidi) but not letter JOINING (no
    HarfBuzz), so raw Arabic renders as disconnected isolated glyphs. Reshaping
    connects the letters; libass then orders the run right-to-left correctly.
    This stays VERBATIM — only glyph forms change, never the words or their order.
    Latin/non-RTL text is returned untouched.
    """
    if not text or not is_rtl(text):
        return text
    try:
        import arabic_reshaper
        return arabic_reshaper.reshape(text)
    except Exception:
        return text


def _ts(seconds: float) -> str:
    """seconds -> ass timestamp H:MM:SS.cc (centisecond precision)."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_color(hex_str: Optional[str], fallback: str = "&H00FFFFFF") -> str:
    """'#RRGGBB' -> ass '&H00BBGGRR' (BGR order, 00 alpha = opaque)."""
    c = (hex_str or "").strip().lstrip("#")
    if len(c) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in c):
        return fallback
    rr, gg, bb = c[0:2], c[2:4], c[4:6]
    return f"&H00{bb}{gg}{rr}".upper()


def _accent(storyboard: Storyboard) -> str:
    """Pick a legible accent for the CTA: a mid/bright palette color, not the
    darkest. Falls back to white."""
    for hexc in (storyboard.palette_hex or []):
        c = (hexc or "").lstrip("#")
        if len(c) == 6:
            try:
                r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
            except ValueError:
                continue
            if r + g + b > 240:  # skip near-black so the CTA reads on dark scenes
                return _ass_color(hexc)
    return "&H00FFFFFF"


def _esc(text: str) -> str:
    """Escape ass-significant characters in verbatim text."""
    return (text or "").replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def build_ass(storyboard: Storyboard, font_family: str) -> str:
    """Return the full .ass document for the storyboard."""
    accent = _accent(storyboard)
    head = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {REEL_W}",
        f"PlayResY: {REEL_H}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
         "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
         "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"),
        # White text, thick dark outline, soft shadow. Alignment 5 = middle-center.
        f"Style: Head,{font_family},96,&H00FFFFFF,&H00FFFFFF,&H00141414,&H64000000,-1,0,0,0,100,100,1,0,1,5,2,5,120,120,0,1",
        f"Style: Sub,{font_family},58,&H00FFFFFF,&H00FFFFFF,&H00141414,&H64000000,0,0,0,0,100,100,0,0,1,4,1,5,140,140,0,1",
        f"Style: CTA,{font_family},64,{accent},{accent},&H00141414,&H64000000,-1,0,0,0,100,100,1,0,1,5,2,5,120,120,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events: list[str] = []
    t = 0.0
    for scene in storyboard.scenes:
        start, end = t, t + scene.duration_s
        t = end
        # Small in/out padding so text doesn't touch the hard cut.
        s0 = start + 0.15
        s1 = max(s0 + 0.4, end - 0.15)
        fad = r"{\fad(350,350)}"

        # Headline — upper-middle.
        if scene.headline:
            txt = _esc(_shape(scene.headline))
            events.append(
                f"Dialogue: 0,{_ts(s0)},{_ts(s1)},Head,0,0,0,,{{\\pos({REEL_W//2},720)}}{fad}{txt}"
            )

        # Sublines — stacked around the vertical center, each revealed slightly
        # after the previous (staggered) for a lively feel.
        if scene.sublines:
            n = len(scene.sublines)
            line_h = 132
            block_top = (REEL_H // 2) - (n - 1) * line_h // 2 + 40
            for i, line in enumerate(scene.sublines):
                y = block_top + i * line_h
                ev_start = min(s1 - 0.3, s0 + i * 0.22)
                events.append(
                    f"Dialogue: 0,{_ts(ev_start)},{_ts(s1)},Sub,0,0,0,,"
                    f"{{\\pos({REEL_W//2},{y})}}{fad}{_esc(_shape(line))}"
                )

        # CTA — lower third.
        if scene.cta_text:
            events.append(
                f"Dialogue: 0,{_ts(s0)},{_ts(s1)},CTA,0,0,0,,"
                f"{{\\pos({REEL_W//2},1480)}}{fad}{_esc(_shape(scene.cta_text))}"
            )

    return "\n".join(head + events) + "\n"
