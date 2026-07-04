"""Kinetic TEXT overlay for the web-app reel (the Motion/Generate path).

The Motion engine (`reel/motion.py`) and the brand-ad generator (`reel/generate.py`)
produce a continuous, cinematic, TEXT-FREE video (that is by design — they are the
background). This module adds the kinetic CAPTION layer ON TOP, at the composition
boundary, so the engines stay pure footage producers.

Approach (mirrors the CLI compositor's verified kinetic overlay, Step 2):
  * Build the content beats from the brand's verbatim brief — a HOOK (headline
    lockup), optional per-scene STORY captions (short LLM narrative lines, timed by
    the generator and GATED by the Evidence Ledger before they reach here), and an
    OUTRO (brand name + the scraped CTA pill; skipped when a brand END-CARD carries
    the pay-off). Minimal text so the cinematic footage stays the star.
  * Render ONE transparent, FULL-DURATION kinetic overlay (Chromium): each beat
    enters with the per-element stagger (`__seektl` drives the same easing as
    `reel/textlayer`), holds in its time window, then fades out before the next.
  * Composite the overlay onto the finished video in a SINGLE ffmpeg overlay pass
    (audio copied through). Best-effort: any failure returns the text-free reel.

GROUNDING: the hook/name/CTA are the brand's verbatim brief; the story captions are LLM
narrative copy that has already passed the Ledger's drop-to-grounded gate (an unsourced
falsifiable claim never reaches this layer). Transforms touch only opacity/translate/scale,
so Arabic shaping/joining is identical in every frame.
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
    _lockup_headline, _logo_data_uri, _LOGO_ANIM, hero_word_count,
)
from poster.template import _hex_to_rgb, _legible_on_dark, _readable_on

_BEAT_FADE = 0.45                       # beat-level cross fade (in/hold handled per element)


# --------------------------------------------------------------------------- #
# Beat planning (pure)                                                          #
# --------------------------------------------------------------------------- #
def plan_beats(headline: str, business_name: str, cta_text: str, total_s: float,
               *, captions: Optional[list[tuple[str, float, float]]] = None,
               include_outro: bool = True) -> list[tuple[ReelScene, float, float]]:
    """Plan the caption beats across a `total_s` video: a HOOK (headline lockup), optional
    per-scene STORY captions (pre-timed (text, t_in, t_out) windows from the generator,
    clipped here so they never collide with the hook/outro), and an OUTRO (brand name +
    CTA pill). Pass `include_outro=False` when a brand END-CARD carries the pay-off instead.
    Returns (scene, t_in, t_out) tuples in time order; windows never overlap and sit
    within [0, total_s]. Empty when there is no usable text."""
    T = max(2.0, float(total_s))
    beats: list[tuple[ReelScene, float, float]] = []
    headline = (headline or "").strip()
    cta_text = (cta_text or "").strip()
    business_name = (business_name or "").strip()

    hook_out = 0.0
    if headline:
        hook = ReelScene(kind="intro", duration_s=3.0, visual_prompt="x", headline=headline)
        hook_out = max(2.4, min(T * 0.5, 5.5))
        # Story captions carry the narrative from the next scene on — the long hook hold was
        # designed for the 2-beat plan and would SWALLOW the early caption windows, so end the
        # hook before the FIRST caption starts (floor 2.4s ≈ the hook scene itself).
        first_cap = min((float(c[1]) for c in (captions or []) if c and str(c[0] or "").strip()),
                        default=None)
        if first_cap is not None:
            hook_out = max(2.4, min(hook_out, first_cap - 0.2))
        beats.append((hook, 0.3, round(hook_out, 2)))

    cta_in = T
    if cta_text and include_outro:
        outro = ReelScene(kind="outro", duration_s=3.0, visual_prompt="x",
                          headline=business_name or None, cta_text=cta_text)
        prev_out = beats[-1][2] if beats else 0.3
        cta_in = min(max(prev_out + 0.3, T * 0.55), max(0.3, T - 2.4))
        if cta_in < T - 0.6:                       # only if there's room to show it
            beats.append((outro, round(cta_in, 2), round(T, 2)))
        else:
            cta_in = T

    # STORY captions (generated mode): each arrives timed to its scene's window; clip it
    # against the hook and the outro so beats never overlap, drop it if too little remains.
    for cap in (captions or []):
        text = (str(cap[0]) if cap and cap[0] else "").strip()
        lo = max(float(cap[1]), (hook_out + 0.2) if hook_out else 0.15)
        hi = min(float(cap[2]), cta_in - 0.2, T - 0.2)
        if not text or hi - lo < 1.2:
            continue
        scene = ReelScene(kind="value_prop", duration_s=max(1.0, min(10.0, hi - lo)),
                          visual_prompt="x", headline=text)
        beats.append((scene, round(lo, 2), round(hi, 2)))

    beats.sort(key=lambda b: b[1])
    return beats


# --------------------------------------------------------------------------- #
# Timeline HTML (one full-duration layer; __seektl drives every beat)          #
# --------------------------------------------------------------------------- #
def _beat_inner(scene: ReelScene, rtl: bool, width: int, logo_uri: Optional[str]) -> str:
    """Logo + scrim + the text cluster for one beat (same structure as a CLI scene)."""
    lockup = scene.kind in ("intro", "outro")
    if lockup and scene.headline:                      # size the HERO by its word count (huge)
        _nh = hero_word_count(scene.headline)
        head_px = round(width * (0.205 if _nh <= 1 else 0.165 if _nh == 2 else 0.13))
    else:
        short = len((scene.headline or "").split()) <= 3
        head_px = round(width * (0.112 if short else 0.088))
    logo_pos = "right:64px" if rtl else "left:64px"
    logo_html = (f'<div class="logo" {_LOGO_ANIM} style="{logo_pos}"><img src="{logo_uri}"></div>'
                 if logo_uri else "")

    inner: list[str] = []
    if scene.headline:
        cls = "headline lockup" if lockup else "headline"
        body = _lockup_headline(scene.headline) if lockup else _highlight_last_word(scene.headline)
        extra = "" if lockup else f" {_anim_attrs(0, 0.26, 46, 'back', 0.94)}"
        inner.append(f'<div class="{cls}"{extra} style="font-size:{head_px}px">{body}</div>')
    if scene.sublines:
        items = "".join(
            f'<div class="item" {_anim_attrs(0.30 + i * 0.15, 0.40, 26, "expo")}>{_atom(s)}</div>'
            for i, s in enumerate(scene.sublines)
        )
        inner.append(f'<div class="items">{items}</div>')
    if scene.cta_text:
        inner.append(f'<div class="cta-wrap" {_CTA_ANIM}>'
                     f'<span class="cta">{_esc(scene.cta_text)}</span></div>')
    cluster = f'<div class="cluster">{"".join(inner)}</div>' if inner else ""
    return f'{logo_html}<div class="scrim"></div><div class="lower">{cluster}</div>'


def _timeline_html(beats: list[tuple[ReelScene, float, float]], sb: Storyboard,
                   width: int, height: int, logo_uri: Optional[str],
                   logo_until: Optional[float] = None) -> str:
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
        f'{_beat_inner(scene, rtl, width, None)}</div>'          # logo is persistent, not per-beat
        for scene, tin, tout in beats
    )
    # Persistent brand logo — top corner, visible the WHOLE reel (owner: "اللوجو لازم يبقا معايا
    # الفيديو كله فوق كدا"), not only on the intro/outro beats.
    logo_corner = "right:56px" if rtl else "left:56px"
    top_logo = (f'<div class="toplogo" style="{logo_corner}"><img src="{logo_uri}"></div>'
                if logo_uri else "")
    logo_h = round(width * 0.11)

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
  .lower{{position:absolute;left:0;right:0;bottom:0;padding:0 84px 332px;box-sizing:border-box;
    display:flex;flex-direction:column;align-items:{edge};}}
  .cluster{{text-align:{align};max-width:86%;}}
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
  /* small SUPPORT line under the hero (hierarchy): readable, not uppercase, no gradient. */
  .lockup .hsub{{display:block;font-size:0.30em;font-family:'Inter','Cairo',system-ui,sans-serif;
    font-weight:600;letter-spacing:0;text-transform:none;line-height:1.2;margin-top:0.34em;
    color:#e9edf3;-webkit-text-fill-color:#e9edf3;-webkit-text-stroke:0;
    text-shadow:{shadow};filter:none;max-width:18ch;}}
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
  /* persistent brand logo — top corner, the whole reel */
  .toplogo{{position:absolute;top:56px;z-index:60;}}
  .toplogo img{{height:{logo_h}px;max-width:40%;object-fit:contain;
    filter:drop-shadow(0 2px 12px rgba(0,0,0,.7));}}
</style></head>
<body><div class="stage">{top_logo}{beat_divs}</div>
<script>
(function(){{
  function _back(p){{var c1=1.70158,c3=c1+1;return 1+c3*Math.pow(p-1,3)+c1*Math.pow(p-1,2);}}
  function _cubic(p){{return 1-Math.pow(1-p,3);}}
  // ease-out-expo — the JS twin of cubic-bezier(0.16,1,0.3,1): fast snap in, long premium settle.
  function _expo(p){{return p>=1?1:1-Math.pow(2,-10*p);}}
  function _seekEls(els,t){{
    for(var i=0;i<els.length;i++){{
      var el=els[i],ds=el.dataset;
      var d=parseFloat(ds.d||'0'),dur=parseFloat(ds.dur||'0.4'),
          dy=parseFloat(ds.dy||'0'),sc=parseFloat(ds.sc||'1'),ease=ds.ease||'expo';
      var p=dur>0?(t-d)/dur:1; if(p<0){{p=0;}} if(p>1){{p=1;}}
      var e=(ease==='back')?_back(p):(ease==='expo')?_expo(p):_cubic(p);
      var op=(t-d)/(dur*0.6); if(op<0){{op=0;}} if(op>1){{op=1;}}
      var ty=dy*(1-e), s=sc+(1-sc)*e;
      el.style.opacity=op;
      el.style.transform='translateY('+ty.toFixed(2)+'px) scale('+s.toFixed(3)+')';
    }}
  }}
  var FADE={_BEAT_FADE};
  // The persistent corner logo hides past LOGO_UNTIL (an appended brand END-CARD carries its
  // own big logo, so the small corner one must fade out during the cross-fade into it).
  var LOGO_UNTIL={(f"{float(logo_until):.2f}" if logo_until else "-1")};
  // Show/animate the beat whose [t_in,t_out) window contains the global time tg.
  window.__seektl=function(tg){{
    var tl=document.querySelector('.toplogo');
    if(tl&&LOGO_UNTIL>0){{var lo=(LOGO_UNTIL-tg)/0.45;tl.style.opacity=Math.max(0,Math.min(1,lo));}}
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
    include_logo: bool = True, logo_until: Optional[float] = None,
) -> str:
    """Render the FULL-DURATION transparent kinetic overlay as an image2 PNG sequence
    (`f0000.png` ... at `fps`). Returns the ffmpeg image2 pattern. Each frame is captured
    by seeking the in-page __seektl(t) driver to an exact timestamp (frame-perfect).
    `logo_until` fades the persistent corner logo out by that timestamp (end-card case)."""
    from playwright.sync_api import sync_playwright

    seq_dir = out_dir / "tl"
    seq_dir.mkdir(parents=True, exist_ok=True)
    logo_uri = _logo_data_uri(sb.logo_url) if include_logo else None
    html = _timeline_html(beats, sb, width, height, logo_uri, logo_until=logo_until)
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
    # NO -shortest here: the PNG sequence's frame count comes from a PROBED duration,
    # so it can run 1-2 frames short of the video — -shortest then truncated the END
    # of the Veo voiceover (measured user bug: "الصوت بيقطع"). The overlay's default
    # eof_action=repeat holds the last text frame; the video input governs the length
    # and the audio is copied through in full.
    run_ffmpeg([
        "-i", str(bg_path),
        "-framerate", str(fps), "-start_number", "0", "-i", seq_pattern,
        "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-preset", "medium", "-crf", "20", "-c:a", "copy",
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


_SHOP_VERBS = ("تسوق", "اشتري", "اطلب الآن", "shop", "buy now", "buy", "order now", "add to cart")
_ECOM_CATS = {"ecommerce", "retail"}


def _category_value(profile: dict) -> str:
    try:
        c = (profile.get("category") or {}) if isinstance(profile, dict) else {}
        v = c.get("value") if isinstance(c, dict) else None
        if isinstance(v, dict):
            v = v.get("value")
        return str(v).lower() if v else ""
    except Exception:
        return ""


def _appropriate_cta(cta: str, profile: dict, rtl: bool) -> str:
    """A telecom / non-ecommerce brand shouldn't say «تسوق»/Shop. Swap a shopping verb for a
    neutral action CTA when the category isn't ecommerce/retail. CTA is design copy (a call to
    action), not a factual claim, so a generic action is fine (two-truth-domains)."""
    low = (cta or "").strip().lower()
    if not low or _category_value(profile) in _ECOM_CATS:
        return cta
    if any(v in low for v in _SHOP_VERBS):
        return "اعرف أكتر" if rtl else "Learn more"
    return cta


def add_kinetic_text_to_reel(profile: dict[str, Any], video_path: str | Path, *,
                             fps: int = 30,
                             captions: Optional[list[tuple[str, float, float]]] = None,
                             footage_s: Optional[float] = None,
                             include_outro: bool = True,
                             hook_override: Optional[str] = None) -> bool:
    """Overlay the kinetic caption layer (HOOK + optional per-scene STORY captions + CTA)
    onto a finished motion/generated reel, IN PLACE. When a brand END-CARD was appended,
    pass `footage_s` (the pre-end-card duration) and `include_outro=False`: the beats stay
    within the footage and the persistent corner logo fades out before the end-card (which
    carries the big logo + CTA itself). Best-effort: returns False (leaving the text-free
    reel intact) on any failure or when there is no usable text. Never raises."""
    try:
        from .from_profile import build_reel_brief, is_rtl

        video_path = Path(video_path)
        if not video_path.is_file():
            return False
        brief = build_reel_brief(profile)
        # The story's FRESH Ledger-gated opener wins; the verbatim brief headline is
        # the fallback (it repeated the SAME tagline on every reel of a brand).
        headline = ((hook_override or "").strip() or (brief.headline or "").strip())
        cta = (brief.cta_text or "").strip()
        name = (brief.business_name or "").strip()
        cap_texts = [str(c[0] or "").strip() for c in (captions or [])]
        if not headline and not cta and not any(cap_texts):
            return False

        rtl = (is_rtl(headline) or is_rtl(name) or is_rtl(cta)
               or any(is_rtl(c) for c in cap_texts if c))
        cta = _appropriate_cta(cta, profile, rtl)        # telecom shouldn't say «تسوق»

        total_s = _probe_duration(video_path) or 10.0
        window_s = min(float(footage_s), total_s) if footage_s else total_s
        beats = plan_beats(headline, name, cta, window_s, captions=captions,
                           include_outro=include_outro)
        if not beats:
            return False

        primary_dir = "rtl" if rtl else "ltr"
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
                logo_until=(window_s if footage_s else None),
            )
            tmp_out = tmpd / "with_text.mp4"
            overlay_timeline_on_video(video_path, pattern, tmp_out, fps=fps)
            shutil.move(str(tmp_out), str(video_path))
        return True
    except Exception:
        return False
