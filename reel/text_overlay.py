"""Kinetic TEXT overlay for the web-app reel (the Motion/Generate path).

The Motion engine (`reel/motion.py`) and the brand-ad generator (`reel/generate.py`)
produce a continuous, cinematic, TEXT-FREE video (that is by design — they are the
background). This module adds the kinetic CAPTION layer ON TOP, at the composition
boundary, so the engines stay pure footage producers.

Approach (mirrors the CLI compositor's verified kinetic overlay, Step 2):
  * Build a 2-beat content storyboard from the brand's verbatim brief — a HOOK
    (headline lockup) and an OUTRO (brand name + the scraped CTA pill). Minimal text
    so the cinematic footage stays the star.
  * Render ONE transparent, FULL-DURATION kinetic overlay (Chromium): each beat
    enters with the per-element stagger (`__seektl` drives the same easing as
    `reel/textlayer`), holds in its time window, then fades out before the next.
  * Composite the overlay onto the finished video in a SINGLE ffmpeg overlay pass
    (audio copied through). Best-effort: any failure returns the text-free reel.

ZERO HALLUCINATION: every word is the brand's verbatim brief; transforms touch only
opacity/translate/scale, so Arabic shaping/joining is identical in every frame.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from .ffmpeg_tools import ffmpeg_exe, run_ffmpeg
from .schemas import REEL_H, REEL_W, ReelScene, Storyboard
from .textlayer import (
    _FONTS_LINK, _accent, _anim_attrs, _atom, _CTA_ANIM, _esc, _highlight_last_word,
    _lockup_headline, _logo_data_uri, _LOGO_ANIM,
)
from poster.template import _hex_to_rgb, _legible_on_dark, _readable_on

_BEAT_FADE = 0.45                       # beat-level cross fade (in/hold handled per element)


# --------------------------------------------------------------------------- #
# Beat planning (pure)                                                          #
# --------------------------------------------------------------------------- #
def plan_beats(headline: str, business_name: str, cta_text: str, total_s: float
               ) -> list[tuple[ReelScene, float, float]]:
    """Plan the minimal HOOK + OUTRO beats across a `total_s` video. Returns
    (scene, t_in, t_out) tuples in time order; windows never overlap and sit
    within [0, total_s]. Empty when there is no usable text."""
    T = max(2.0, float(total_s))
    beats: list[tuple[ReelScene, float, float]] = []
    headline = (headline or "").strip()
    cta_text = (cta_text or "").strip()
    business_name = (business_name or "").strip()

    if headline:
        hook = ReelScene(kind="intro", duration_s=3.0, visual_prompt="x", headline=headline)
        hook_out = max(2.4, min(T * 0.5, 5.5))
        beats.append((hook, 0.3, round(hook_out, 2)))

    if cta_text:
        outro = ReelScene(kind="outro", duration_s=3.0, visual_prompt="x",
                          headline=business_name or None, cta_text=cta_text)
        prev_out = beats[-1][2] if beats else 0.3
        cta_in = min(max(prev_out + 0.3, T * 0.55), max(0.3, T - 2.4))
        if cta_in < T - 0.6:                       # only if there's room to show it
            beats.append((outro, round(cta_in, 2), round(T, 2)))
    return beats


# --------------------------------------------------------------------------- #
# Timeline HTML (one full-duration layer; __seektl drives every beat)          #
# --------------------------------------------------------------------------- #
def _beat_inner(scene: ReelScene, rtl: bool, width: int, logo_uri: Optional[str]) -> str:
    """Logo + scrim + the text cluster for one beat (same structure as a CLI scene)."""
    short = len((scene.headline or "").split()) <= 3
    head_px = round(width * (0.112 if short else 0.088))
    lockup = scene.kind in ("intro", "outro")
    logo_pos = "right:64px" if rtl else "left:64px"
    logo_html = (f'<div class="logo" {_LOGO_ANIM} style="{logo_pos}"><img src="{logo_uri}"></div>'
                 if logo_uri else "")

    inner: list[str] = []
    if scene.headline:
        cls = "headline lockup" if lockup else "headline"
        body = _lockup_headline(scene.headline) if lockup else _highlight_last_word(scene.headline)
        extra = "" if lockup else f" {_anim_attrs(0, 0.36, 46, 'back', 0.94)}"
        inner.append(f'<div class="{cls}"{extra} style="font-size:{head_px}px">{body}</div>')
    if scene.sublines:
        items = "".join(
            f'<div class="item" {_anim_attrs(0.30 + i * 0.15, 0.40, 26, "cubic")}>{_atom(s)}</div>'
            for i, s in enumerate(scene.sublines)
        )
        inner.append(f'<div class="items">{items}</div>')
    if scene.cta_text:
        inner.append(f'<div class="cta-wrap" {_CTA_ANIM}>'
                     f'<span class="cta">{_esc(scene.cta_text)}</span></div>')
    cluster = f'<div class="cluster">{"".join(inner)}</div>' if inner else ""
    return f'{logo_html}<div class="scrim"></div><div class="lower">{cluster}</div>'


def _timeline_html(beats: list[tuple[ReelScene, float, float]], sb: Storyboard,
                   width: int, height: int, logo_uri: Optional[str]) -> str:
    rtl = sb.primary_dir == "rtl"
    dir_attr = "rtl" if rtl else "ltr"
    accent = _accent(sb)
    accent_rgb = _hex_to_rgb(accent)
    accent_on_dark = _legible_on_dark(accent_rgb)
    chip_text = _readable_on(accent_rgb)
    _pal2 = [str(c) for c in ([sb.primary_color] + list(sb.palette_hex or []))
             if c and str(c).startswith("#") and str(c).lower() != accent.lower()]
    accent2 = _pal2[0] if _pal2 else accent

    item_px = round(width * 0.046)
    cta_px = round(width * 0.048)
    logo_h = round(width * 0.12)
    edge = "flex-end" if rtl else "flex-start"
    align = "right" if rtl else "left"
    spine = "border-right" if rtl else "border-left"
    spine_pad = "padding-right" if rtl else "padding-left"
    head_track = "0" if rtl else "-0.5px"
    lock_track = "0" if rtl else "-1px"
    shadow = "0 2px 10px rgba(0,0,0,.9), 0 1px 3px rgba(0,0,0,.95)"

    beat_divs = "".join(
        f'<div class="beat" data-tin="{tin:.2f}" data-tout="{tout:.2f}">'
        f'{_beat_inner(scene, rtl, width, logo_uri)}</div>'
        for scene, tin, tout in beats
    )

    return f"""<!doctype html><html dir="{dir_attr}" lang="ar"><head><meta charset="utf-8">
{_FONTS_LINK}
<style>
  html,body{{margin:0;padding:0;width:{width}px;height:{height}px;background:transparent;}}
  .stage{{position:relative;width:{width}px;height:{height}px;
    font-family:'Space Grotesk','Cairo',system-ui,sans-serif;color:#fff;overflow:hidden;
    --accent:{accent_on_dark};}}
  .beat{{position:absolute;inset:0;opacity:0;}}
  .scrim{{position:absolute;left:0;right:0;bottom:0;height:64%;
    background:linear-gradient(to top,
      rgba(6,9,14,.96) 0%, rgba(6,9,14,.92) 20%, rgba(6,9,14,.74) 42%,
      rgba(6,9,14,.34) 66%, rgba(6,9,14,0) 100%);}}
  .lower{{position:absolute;left:0;right:0;bottom:0;padding:0 72px 300px;box-sizing:border-box;
    display:flex;flex-direction:column;align-items:{edge};}}
  .cluster{{{spine}:9px solid var(--accent);{spine_pad}:30px;text-align:{align};max-width:88%;}}
  .cluster>*{{unicode-bidi:plaintext;}}
  .headline{{font-family:'Oswald','Cairo',system-ui,sans-serif;font-weight:700;
    line-height:1.0;letter-spacing:{head_track};text-transform:uppercase;
    text-wrap:balance;text-shadow:{shadow};-webkit-text-stroke:0.4px rgba(0,0,0,.3);}}
  .headline .hl{{color:var(--accent);}}
  .headline.lockup{{display:flex;flex-direction:column;gap:2px;line-height:.92;
    letter-spacing:{lock_track};text-shadow:none;-webkit-text-stroke:0;}}
  .lockup .lw{{display:block;
    background:linear-gradient(180deg,#ffffff 0%,#d7dee7 100%);
    -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent;
    -webkit-text-stroke:1.4px rgba(6,9,14,.72);
    filter:drop-shadow(0 3px 8px rgba(0,0,0,.92)) drop-shadow(0 12px 26px rgba(0,0,0,.6));}}
  .lockup .lw.acc{{
    background:linear-gradient(180deg,{accent} 0%,{accent2} 100%);
    -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent;
    -webkit-text-stroke:1.2px rgba(6,9,14,.42);
    filter:drop-shadow(0 3px 8px rgba(0,0,0,.9));}}
  .items{{margin-top:4px;}}
  .item{{font-family:'Inter','Cairo',system-ui,sans-serif;font-weight:600;
    font-size:{item_px}px;line-height:1.5;margin:0.06em 0;letter-spacing:0.2px;text-shadow:{shadow};}}
  .cta-wrap{{margin-top:32px;}}
  .cta{{display:inline-block;font-family:'Space Grotesk','Cairo',sans-serif;font-weight:700;
    font-size:{cta_px}px;background:{accent};color:{chip_text};padding:0.54em 1.5em;
    border-radius:999px;letter-spacing:0.3px;box-shadow:0 10px 30px rgba(0,0,0,.55);}}
  .logo{{position:absolute;top:64px;}}
  .logo img{{height:{logo_h}px;max-width:42%;object-fit:contain;
    filter:drop-shadow(0 2px 14px rgba(0,0,0,.6));}}
  [data-anim]{{opacity:0;will-change:transform,opacity;}}
</style></head>
<body><div class="stage">{beat_divs}</div>
<script>
(function(){{
  function _back(p){{var c1=1.70158,c3=c1+1;return 1+c3*Math.pow(p-1,3)+c1*Math.pow(p-1,2);}}
  function _cubic(p){{return 1-Math.pow(1-p,3);}}
  function _seekEls(els,t){{
    for(var i=0;i<els.length;i++){{
      var el=els[i],ds=el.dataset;
      var d=parseFloat(ds.d||'0'),dur=parseFloat(ds.dur||'0.4'),
          dy=parseFloat(ds.dy||'0'),sc=parseFloat(ds.sc||'1'),ease=ds.ease||'cubic';
      var p=dur>0?(t-d)/dur:1; if(p<0){{p=0;}} if(p>1){{p=1;}}
      var e=(ease==='back')?_back(p):_cubic(p);
      var op=(t-d)/(dur*0.6); if(op<0){{op=0;}} if(op>1){{op=1;}}
      var ty=dy*(1-e), s=sc+(1-sc)*e;
      el.style.opacity=op;
      el.style.transform='translateY('+ty.toFixed(2)+'px) scale('+s.toFixed(3)+')';
    }}
  }}
  var FADE={_BEAT_FADE};
  // Show/animate the beat whose [t_in,t_out) window contains the global time tg.
  window.__seektl=function(tg){{
    var beats=document.querySelectorAll('.beat');
    for(var b=0;b<beats.length;b++){{
      var beat=beats[b],tin=parseFloat(beat.dataset.tin),tout=parseFloat(beat.dataset.tout);
      if(tg<tin||tg>=tout){{beat.style.opacity=0;continue;}}
      var bf=(tg>tout-FADE)?Math.max(0,(tout-tg)/FADE):1;
      beat.style.opacity=bf;
      _seekEls(beat.querySelectorAll('[data-anim]'),tg-tin);
    }}
  }};
  window.__seektl(0);
}})();
</script>
</body></html>"""


def render_timeline_overlay(
    sb: Storyboard, beats: list[tuple[ReelScene, float, float]], *,
    width: int, height: int, fps: int, total_s: float, out_dir: Path,
    include_logo: bool = True,
) -> str:
    """Render the FULL-DURATION transparent kinetic overlay as an image2 PNG sequence
    (`f0000.png` ... at `fps`). Returns the ffmpeg image2 pattern. Each frame is captured
    by seeking the in-page __seektl(t) driver to an exact timestamp (frame-perfect)."""
    from playwright.sync_api import sync_playwright

    seq_dir = out_dir / "tl"
    seq_dir.mkdir(parents=True, exist_ok=True)
    logo_uri = _logo_data_uri(sb.logo_url) if include_logo else None
    html = _timeline_html(beats, sb, width, height, logo_uri)
    n = max(1, round(float(total_s) * fps))
    clip = {"x": 0, "y": 0, "width": width, "height": height}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height},
                                    device_scale_factor=1)
            page.set_content(html, wait_until="networkidle")
            try:
                page.evaluate("async () => { await document.fonts.ready; }")
            except Exception:
                pass
            for f in range(n):
                page.evaluate("(t) => window.__seektl(t)", f / float(fps))
                page.screenshot(path=str(seq_dir / f"f{f:04d}.png"),
                                omit_background=True, clip=clip)
            page.close()
        finally:
            browser.close()
    return str(seq_dir / "f%04d.png")


def overlay_timeline_on_video(bg_path: Path, seq_pattern: str, out_path: Path, *,
                              fps: int = 30, width: int = REEL_W, height: int = REEL_H) -> Path:
    """Composite the full-duration transparent overlay onto the video in ONE pass; the
    source audio is copied through. The overlay sequence is the same length as the video."""
    fc = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},format=yuv420p[bg];"
        f"[1:v]format=rgba,fps={fps}[tx];"
        f"[bg][tx]overlay=0:0:format=auto,format=yuv420p[v]"
    )
    run_ffmpeg([
        "-i", str(bg_path),
        "-framerate", str(fps), "-start_number", "0", "-i", seq_pattern,
        "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-preset", "medium", "-crf", "20", "-c:a", "copy", "-shortest",
        "-movflags", "+faststart", str(out_path),
    ])
    return out_path


def _probe_duration(path: Path) -> Optional[float]:
    """Video duration in seconds, parsed from ffmpeg's stderr (no ffprobe needed)."""
    try:
        out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)],
                             capture_output=True, text=True, timeout=60).stderr or ""
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
        if m:
            h, mn, s = m.groups()
            return int(h) * 3600 + int(mn) * 60 + float(s)
    except Exception:
        pass
    return None


def add_kinetic_text_to_reel(profile: dict[str, Any], video_path: str | Path, *,
                             fps: int = 30) -> bool:
    """Overlay the kinetic HOOK + CTA caption layer onto a finished motion/generated reel,
    IN PLACE. Best-effort: returns False (leaving the text-free reel intact) on any failure
    or when the brand brief has no usable headline/CTA. Never raises."""
    try:
        from .from_profile import build_reel_brief, is_rtl

        video_path = Path(video_path)
        if not video_path.is_file():
            return False
        brief = build_reel_brief(profile)
        headline = (brief.headline or "").strip()
        cta = (brief.cta_text or "").strip()
        name = (brief.business_name or "").strip()
        if not headline and not cta:
            return False

        total_s = _probe_duration(video_path) or 10.0
        beats = plan_beats(headline, name, cta, total_s)
        if not beats:
            return False

        primary_dir = "rtl" if (is_rtl(headline) or is_rtl(name)) else "ltr"
        sb = Storyboard(
            business_name=name or "brand", primary_dir=primary_dir,
            palette_hex=list(brief.palette_hex[:6]),
            primary_color=(brief.palette_hex[0] if brief.palette_hex else None),
            logo_url=brief.logo_url,
        )

        with tempfile.TemporaryDirectory(prefix="reeltext_") as tmp:
            tmpd = Path(tmp)
            pattern = render_timeline_overlay(
                sb, beats, width=REEL_W, height=REEL_H, fps=fps, total_s=total_s, out_dir=tmpd,
            )
            tmp_out = tmpd / "with_text.mp4"
            overlay_timeline_on_video(video_path, pattern, tmp_out, fps=fps)
            shutil.move(str(tmp_out), str(video_path))
        return True
    except Exception:
        return False
