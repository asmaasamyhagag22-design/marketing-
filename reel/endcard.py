"""A strong, unmistakable BRAND END-CARD for the reel (the owner: "فين WE؟").

The AI-generated footage is deliberately TEXT-FREE (Imagen/Veo bake garbled text/logos), so the
brand identity can't live INSIDE the scenes — it must come from a COMPOSITED overlay we control.
This appends a clean ~2.5s end-card — the real brand LOGO big, on the brand-colour, with the CTA —
so the reel ends on a clear "this is WE" moment. Rendered via Chromium (Arabic-safe), then
xfade-appended to the finished reel. Best-effort: returns False and leaves the reel untouched on
any failure. Never raises.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from reel.ffmpeg_tools import run_ffmpeg
from reel.schemas import REEL_H, REEL_W


def _endcard_html(logo_uri: Optional[str], name: str, cta: str, accent: str, accent2: str,
                  rtl: bool, width: int, height: int) -> str:
    align = "center"
    logo_block = (f'<img class="logo" src="{logo_uri}">' if logo_uri else "")
    cta_block = f'<div class="cta">{cta}</div>' if cta else ""
    name_block = f'<div class="name">{name}</div>' if name else ""
    return f"""<!doctype html><html dir="{'rtl' if rtl else 'ltr'}" lang="ar"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@700&family=Cairo:wght@700;800&display=swap" rel="stylesheet">
<style>
 html,body{{margin:0;padding:0;width:{width}px;height:{height}px;}}
 .card{{position:relative;width:{width}px;height:{height}px;overflow:hidden;
   font-family:'Space Grotesk','Cairo',system-ui,sans-serif;color:#fff;text-align:{align};
   background:radial-gradient(120% 90% at 50% 38%, {accent} 0%, {accent2} 55%, #05070c 100%);}}
 /* soft light-beam motif — a premium, brand-coloured GRAPHIC (universal; never tints people) */
 .beam{{position:absolute;left:50%;top:-10%;width:8px;height:120%;transform-origin:top center;
   background:linear-gradient(to bottom, rgba(255,255,255,.55), rgba(255,255,255,0));
   filter:blur(3px);opacity:.5;}}
 .b1{{transform:translateX(-50%) rotate(-18deg);}}
 .b2{{transform:translateX(-50%) rotate(0deg);opacity:.35;}}
 .b3{{transform:translateX(-50%) rotate(18deg);}}
 .wrap{{position:absolute;left:0;right:0;top:50%;transform:translateY(-50%);
   display:flex;flex-direction:column;align-items:center;gap:38px;padding:0 90px;box-sizing:border-box;}}
 .logo{{height:{round(height*0.16)}px;max-width:76%;object-fit:contain;
   filter:drop-shadow(0 6px 30px rgba(0,0,0,.6));}}
 .name{{font-family:'Cairo','Space Grotesk',sans-serif;font-weight:800;
   font-size:{round(width*0.075)}px;letter-spacing:0.5px;text-shadow:0 3px 18px rgba(0,0,0,.6);}}
 .cta{{display:inline-block;font-weight:800;font-size:{round(width*0.05)}px;
   background:#fff;color:#111;padding:0.6em 1.8em;border-radius:999px;
   box-shadow:0 12px 34px rgba(0,0,0,.5);}}
</style></head>
<body><div class="card">
 <div class="beam b1"></div><div class="beam b2"></div><div class="beam b3"></div>
 <div class="wrap">{logo_block}{name_block}{cta_block}</div>
</div></body></html>"""


def render_endcard(profile: dict, out_png: Path, *, width: int = REEL_W, height: int = REEL_H) -> Optional[Path]:
    """Render the brand end-card to a PNG via Chromium (Arabic shapes correctly). None on failure."""
    try:
        from playwright.sync_api import sync_playwright

        from reel.from_profile import build_reel_brief, is_rtl
        from reel.text_overlay import _appropriate_cta
        from reel.textlayer import _logo_data_uri

        brief = build_reel_brief(profile)
        name = (brief.business_name or "").strip()
        cta = _appropriate_cta((brief.cta_text or "").strip() or ("اعرف أكتر" if is_rtl(name) else "Learn more"),
                               profile, is_rtl(name))
        pal = [c for c in (brief.palette_hex or []) if isinstance(c, str) and c.startswith("#")]
        accent = pal[0] if pal else "#1b2340"
        accent2 = pal[1] if len(pal) > 1 else accent
        logo_uri = _logo_data_uri(brief.logo_url) if brief.logo_url else None
        html = _endcard_html(logo_uri, name, cta, accent, accent2, is_rtl(name), width, height)

        out_png = Path(out_png)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
                page.set_content(html, wait_until="networkidle")
                try:
                    page.evaluate("async () => { await document.fonts.ready; }")
                except Exception:
                    pass
                page.screenshot(path=str(out_png), clip={"x": 0, "y": 0, "width": width, "height": height})
            finally:
                browser.close()
        return out_png if out_png.exists() else None
    except Exception:
        return None


def append_endcard_to_reel(profile: dict, video_path: str | Path, *, seconds: float = 2.6,
                           fps: int = 30, width: int = REEL_W, height: int = REEL_H) -> bool:
    """Append a ~`seconds` brand end-card (gentle push-in + fade) to the reel, IN PLACE, with a
    short cross-fade from the last scene. Best-effort: returns False (reel untouched) on failure."""
    try:
        from reel.motion import _clip_duration

        video_path = Path(video_path)
        if not video_path.is_file():
            return False
        work = video_path.parent
        png = render_endcard(profile, work / "_endcard.png", width=width, height=height)
        if png is None:
            return False

        # end-card -> a clip: slow push-in + fade-in
        card = work / "_endcard.mp4"
        frames = int(seconds * fps)
        vf = (f"scale={width}:{height},zoompan=z='1.0+0.05*on/{frames}':d={frames}:"
              f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},"
              f"fade=t=in:st=0:d=0.4,format=yuv420p")
        run_ffmpeg(["-loop", "1", "-i", str(png), "-t", f"{seconds:.2f}", "-vf", vf, "-r", str(fps),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20", str(card)])

        # xfade the reel -> the end-card
        t = 0.5
        main_dur = _clip_duration(video_path)
        off = max(0.0, main_dur - t)
        out = work / "_with_endcard.mp4"
        graph = (f"[0:v]settb=AVTB,fps={fps}[a];[1:v]settb=AVTB,fps={fps}[b];"
                 f"[a][b]xfade=transition=fade:duration={t}:offset={off:.2f}[v]")
        run_ffmpeg(["-i", str(video_path), "-i", str(card), "-filter_complex", graph, "-map", "[v]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
                    "-profile:v", "high", "-preset", "medium", "-crf", "20", str(out)])
        import shutil
        shutil.move(str(out), str(video_path))
        for f in (png, card):
            try:
                Path(f).unlink()
            except OSError:
                pass
        return True
    except Exception:
        return False
