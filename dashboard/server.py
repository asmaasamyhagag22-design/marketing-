"""Baseera Studio - a LOCAL, INTERACTIVE marketing web app.

    python -m dashboard.server              # -> http://127.0.0.1:8770  (opens the browser)
    python -m dashboard.server --port 9000 --no-open

Paste a brand URL, press Analyze, and WATCH the fast core run (scrape -> profile -> competitors
-> SWOT -> content calendar). Then you land INSIDE the dashboard - the SWOT, competitors and
calendar are there, and a Creative Studio lets you GENERATE on demand: press "Generate poster" for
an image, "Generate reel" for the video, and Regenerate until it's right. Every stage streams over
SSE. Heavy generation (Veo/Imagen) runs only when YOU ask for it - the owner wanted to sit in the
heart of the dashboard and drive it, not wait for a one-shot report.

Stdlib-only (http.server + threads): no framework, no async, no build step. The heavy lifting is
the SAME tested pipeline (dashboard.run.analyze / generate_poster / generate_reel).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dashboard import run as _run_mod
from dashboard.build import build_dashboard_html

# Baseera palette (in lock-step with dashboard/build.py::_C so studio + dashboard read as one).
_C = {
    "bg": "#FAF5F1", "surface": "#FFFFFF", "ink": "#2A1A1F", "inkSoft": "#5C4A52",
    "muted": "#9B8A92", "line": "rgba(168,69,107,0.14)",
    "blush100": "#F6E0E7", "blush500": "#B85C7A", "blush600": "#9C4564", "blush700": "#7E3450",
    "ok": "#3F8F6B", "bad": "#B54848", "gold": "#C68A3C",
}

_SLUG_RE = re.compile(r"^[A-Za-z0-9_]+$")

# One in-flight generation per (slug, kind) across all request threads — a duplicate request
# (refresh / second tab / SSE reconnect) is rejected instead of racing on the same output file.
_INFLIGHT: set = set()
_INFLIGHT_LOCK = threading.Lock()


def sse(event: str, data) -> bytes:
    """Format one Server-Sent Event frame (JSON-encoded data, so newlines can't break framing)."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def _ok_slug(slug: str) -> bool:
    return bool(slug) and bool(_SLUG_RE.match(slug))


# ------------------------------------------------------------------------------------------------
# Landing page (URL -> Analyze -> redirect to the studio)
# ------------------------------------------------------------------------------------------------
def _landing_html() -> str:
    c = _C
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Baseera Studio</title>
<style>
  :root{{color-scheme:light;}} *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
    color:{c['ink']};background:{c['bg']};line-height:1.5;-webkit-font-smoothing:antialiased;
    background-image:
      radial-gradient(circle at 8% 4%,rgba(236,203,214,.38) 0%,transparent 26%),
      radial-gradient(circle at 94% 8%,rgba(240,228,211,.30) 0%,transparent 28%),
      radial-gradient(circle at 4% 98%,rgba(246,224,231,.36) 0%,transparent 28%);
    min-height:100vh;padding:34px clamp(14px,4vw,44px) 60px;}}
  .serif{{font-family:'Fraunces',Georgia,'Times New Roman',serif;}}
  .wrap{{max-width:900px;margin:0 auto;}}
  .brand{{display:flex;align-items:center;gap:11px;margin-bottom:22px;}}
  .dot{{width:34px;height:34px;border-radius:11px;flex:none;
    background:linear-gradient(135deg,{c['blush500']},{c['blush700']});box-shadow:0 6px 16px rgba(158,69,100,.28);}}
  .brand-n{{font-family:'Fraunces',Georgia,serif;font-weight:600;font-size:22px;letter-spacing:-.3px;}}
  .brand-t{{font-size:12px;color:{c['muted']};letter-spacing:.4px;text-transform:uppercase;}}
  .card{{background:{c['surface']};border:1px solid {c['line']};border-radius:20px;
    padding:clamp(20px,4vw,34px);box-shadow:0 14px 40px rgba(126,52,80,.09);}}
  h1{{font-family:'Fraunces',Georgia,serif;font-weight:600;font-size:clamp(24px,4vw,34px);
    line-height:1.12;letter-spacing:-.6px;margin-bottom:8px;}} h1 em{{font-style:normal;color:{c['blush600']};}}
  .sub{{color:{c['inkSoft']};font-size:15px;max-width:60ch;margin-bottom:24px;}}
  .row{{display:flex;gap:10px;flex-wrap:wrap;}}
  input[type=url]{{flex:1 1 340px;min-width:0;padding:14px 16px;font-size:15px;border:1.5px solid {c['line']};
    border-radius:12px;background:#fff;color:{c['ink']};font-family:inherit;}}
  input[type=url]:focus{{outline:none;border-color:{c['blush500']};box-shadow:0 0 0 4px rgba(184,92,122,.14);}}
  button{{padding:14px 26px;font-size:15px;font-weight:600;font-family:inherit;cursor:pointer;color:#fff;
    border:none;border-radius:12px;white-space:nowrap;background:linear-gradient(135deg,{c['blush500']},{c['blush700']});
    box-shadow:0 8px 20px rgba(158,69,100,.26);transition:transform .12s,opacity .12s;}}
  button:hover:not(:disabled){{transform:translateY(-1px);}} button:disabled{{opacity:.5;cursor:not-allowed;}}
  .stage-strip{{display:flex;flex-wrap:wrap;gap:7px;margin-top:24px;}}
  .chip{{font-size:11.5px;font-weight:600;padding:6px 12px;border-radius:999px;background:#fff;
    border:1px solid {c['line']};color:{c['muted']};transition:all .2s;}}
  .chip.run{{color:{c['blush700']};border-color:{c['blush500']};background:{c['blush100']};animation:pulse 1.1s ease-in-out infinite;}}
  .chip.ok{{color:{c['ok']};border-color:rgba(63,143,107,.4);background:rgba(63,143,107,.09);}}
  .chip.bad{{color:{c['bad']};border-color:rgba(181,72,72,.4);background:rgba(181,72,72,.08);}}
  @keyframes pulse{{0%,100%{{opacity:1;}}50%{{opacity:.55;}}}}
  #log{{margin-top:18px;background:#2A1A1F;color:#F3E7EC;border-radius:14px;padding:16px 18px;
    font-family:'Space Grotesk',ui-monospace,Consolas,monospace;font-size:12.5px;line-height:1.7;
    max-height:300px;overflow:auto;display:none;white-space:pre-wrap;word-break:break-word;}}
  #log .l-ok{{color:#8FE0B8;}} #log .l-bad{{color:#F3A8A8;}} #log .l-run{{color:#E8C7D4;}}
  .foot{{text-align:center;color:{c['muted']};font-size:12px;margin-top:26px;}}
</style></head><body>
<div class="wrap">
  <div class="brand"><div class="dot"></div>
    <div><div class="brand-n">Baseera Studio</div><div class="brand-t">Marketing Intelligence</div></div></div>
  <div class="card">
    <h1 class="serif">One URL in, a <em>campaign you drive</em>.</h1>
    <p class="sub">Paste a brand's website. Baseera studies it — profile, cited SWOT, real
      competitors, a content calendar — then hands you a live dashboard where you generate the
      poster and the reel on demand, and regenerate until they're right.</p>
    <div class="row">
      <input id="url" type="url" placeholder="https://your-brand.com" autocomplete="off" spellcheck="false">
      <button id="go">Analyze</button>
    </div>
    <div id="strip" class="stage-strip" style="display:none"></div>
    <div id="log"></div>
  </div>
  <div class="foot">Runs locally. Heavy generation only happens when you ask for it.</div>
</div>
<script>
const STAGES=["Scrape + Profile + Competitors + SWOT","Content calendar"];
const $=s=>document.querySelector(s);
const url=$("#url"),go=$("#go"),strip=$("#strip"),log=$("#log"); let es=null;
function chips(){{strip.innerHTML="";strip.style.display="flex";
  STAGES.forEach(s=>{{const d=document.createElement("div");d.className="chip";d.dataset.k=s;
    d.textContent=s.replace(" + Competitors + SWOT","...");strip.appendChild(d);}});}}
function setChip(label,cls){{const el=[...strip.children].find(c=>label.startsWith(c.dataset.k.split(" ...")[0].split(" +")[0])||c.dataset.k===label); if(el)el.className="chip "+cls;}}
function line(t){{const d=document.createElement("div");
  if(t.includes("[OK]"))d.className="l-ok";else if(t.includes("[X]"))d.className="l-bad";
  else if(t.trim().startsWith("->"))d.className="l-run";d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight;}}
go.onclick=()=>{{const u=url.value.trim();if(!u){{url.focus();return;}}
  if(es)es.close();go.disabled=true;log.style.display="block";log.innerHTML="";chips();
  line("* Baseera - analyzing "+u+"\\n");
  es=new EventSource("/analyze?url="+encodeURIComponent(u));
  es.addEventListener("stage",e=>{{const d=JSON.parse(e.data);line(d.msg);
    if(d.event==="stage_start")setChip(d.label,"run");else if(d.event==="stage_ok")setChip(d.label,"ok");
    else if(d.event==="stage_fail")setChip(d.label,"bad");}});
  es.addEventListener("done",e=>{{const d=JSON.parse(e.data);es.close();
    line("\\n[OK] opening your studio ...");window.location="/studio?slug="+encodeURIComponent(d.slug);}});
  es.addEventListener("failed",e=>{{const d=JSON.parse(e.data);es.close();go.disabled=false;
    line("\\n[X] "+(d.msg||"analysis failed"));}});
  es.onerror=()=>{{if(es.readyState===EventSource.CLOSED)go.disabled=false;}};}};
url.addEventListener("keydown",e=>{{if(e.key==="Enter")go.click();}});
</script></body></html>"""


# ------------------------------------------------------------------------------------------------
# Studio page (the report body + an interactive Creative Studio)
# ------------------------------------------------------------------------------------------------
def _panel(kind: str, icon: str, title: str, sub: str, has_asset: bool, slug: str) -> str:
    """One Creative-Studio panel: a stage (asset or placeholder) + log + a generate/regenerate button."""
    asset_url = f"/asset?slug={slug}&amp;kind={kind}"
    reel_cls = " is-reel" if kind == "reel" else ""
    if has_asset and kind == "poster":
        stage_cls, inner = f"cst-stage{reel_cls} has-asset", f'<img src="{asset_url}" alt="poster">'
    elif has_asset and kind == "reel":
        stage_cls = f"cst-stage{reel_cls} has-asset"
        inner = f'<video src="{asset_url}" controls playsinline preload="metadata"></video>'
    else:
        stage_cls = f"cst-stage{reel_cls}"
        hint = ("generates automatically" if kind == "poster"
                else "press Generate — Veo takes ~10–20 min")
        inner = (f'<div class="cst-empty">{icon}<span>Not generated yet</span>'
                 f'<small>{hint}</small></div>')
    btn = "Regenerate" if has_asset else f"Generate {kind}"
    return f"""<div class="cst-panel" id="{kind}-panel">
      <div class="cst-head">{icon} {title} <span class="cst-sub">{sub}</span></div>
      <div class="{stage_cls}" id="{kind}-stage">{inner}</div>
      <div class="cst-log" id="{kind}-log"></div>
      <button class="cst-btn" id="{kind}-btn" onclick="gen('{kind}')">{btn}</button>
    </div>"""


def _studio_css() -> str:
    c = _C
    return f"""<style>
    .cst-wrap{{max-width:1180px;margin:0 auto;}}
    .cst-grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;}}
    @media(max-width:760px){{.cst-grid{{grid-template-columns:1fr;}}}}
    .cst-panel{{background:{c['surface']};border:1px solid {c['line']};border-radius:16px;padding:16px;
      display:flex;flex-direction:column;gap:12px;box-shadow:0 8px 24px rgba(126,52,80,.06);}}
    .cst-head{{font-family:'Fraunces',Georgia,serif;font-weight:600;font-size:16px;display:flex;
      align-items:center;gap:8px;}}
    .cst-sub{{margin-left:auto;font-size:11px;font-weight:400;color:{c['muted']};font-family:'Inter',sans-serif;}}
    .cst-stage{{position:relative;border-radius:12px;overflow:hidden;display:flex;align-items:center;
      justify-content:center;min-height:240px;
      background:linear-gradient(140deg,{c['blush100']},#F3E9DD);
      border:1.5px dashed rgba(168,69,107,0.30);}}
    .cst-stage.is-reel{{aspect-ratio:9/16;max-height:520px;margin:0 auto;width:auto;min-height:0;}}
    .cst-stage.has-asset{{background:#0e0e13;border:1px solid {c['line']};border-style:solid;}}
    .cst-stage img,.cst-stage video{{width:100%;height:auto;display:block;}}
    .cst-stage.is-reel video{{height:100%;object-fit:contain;}}
    .cst-empty{{display:flex;flex-direction:column;align-items:center;gap:9px;color:{c['blush600']};
      font-size:30px;padding:30px 14px;text-align:center;}}
    .cst-empty span{{font-size:13.5px;font-weight:600;color:{c['inkSoft']};}}
    .cst-empty small{{font-size:11.5px;color:{c['muted']};font-weight:400;}}
    .cst-stage.is-gen{{border-style:solid;border-color:rgba(184,92,122,.38);}}
    .cst-stage.is-gen::after{{content:'';position:absolute;inset:0;pointer-events:none;
      background:linear-gradient(100deg,transparent 25%,rgba(184,92,122,.16) 50%,transparent 75%);
      background-size:220% 100%;animation:cstshim 1.5s linear infinite;}}
    @keyframes cstshim{{from{{background-position:220% 0}}to{{background-position:-220% 0}}}}
    @media(prefers-reduced-motion:reduce){{.cst-stage.is-gen::after{{animation:none}}}}
    .cst-log{{display:none;background:#2A1A1F;color:#F3E7EC;border-radius:10px;padding:11px 13px;
      font-family:'Space Grotesk',ui-monospace,Consolas,monospace;font-size:11.5px;line-height:1.65;
      max-height:150px;overflow:auto;white-space:pre-wrap;word-break:break-word;}}
    .cst-log .l-ok{{color:#8FE0B8;}} .cst-log .l-bad{{color:#F3A8A8;}} .cst-log .l-run{{color:#E8C7D4;}}
    .cst-btn{{padding:12px;font-size:14px;font-weight:600;font-family:'Inter',sans-serif;cursor:pointer;
      color:#fff;border:none;border-radius:11px;background:linear-gradient(135deg,{c['blush500']},{c['blush700']});
      box-shadow:0 8px 18px rgba(158,69,100,.22);transition:transform .12s,opacity .12s;}}
    .cst-btn:hover:not(:disabled){{transform:translateY(-1px);}} .cst-btn:disabled{{opacity:.55;cursor:not-allowed;}}
    .cst-bar{{display:flex;gap:10px;align-items:center;max-width:1180px;margin:0 auto 4px;padding:0 4px;}}
    .cst-bar a{{margin-left:auto;font-size:13px;color:{c['blush600']};text-decoration:none;font-weight:600;}}
    </style>"""


def _studio_section(slug: str, has_poster: bool, has_reel: bool) -> str:
    """The interactive Creative Studio block (uses the dashboard's own .sec/.card/.bar classes)."""
    return f"""<div class="sec"><div class="sec-h"><span class="bar"></span>
      <h2>Creative Studio — generate on demand</h2><span class="cnt">grounded · brand-safe · yours to drive</span></div>
      <div class="card"><div class="cst-grid">
        {_panel('poster', '🎨', 'Poster', 'one-shot · crisp logo', has_poster, slug)}
        {_panel('reel', '🎬', 'Reel', 'Veo 3.1 · branded end-card', has_reel, slug)}
      </div></div></div>"""


def _studio_js(slug: str, auto_poster: bool, auto_reel: bool) -> str:
    return f"""<script>
const SLUG={json.dumps(slug)};
const AUTO={{poster:{str(auto_poster).lower()},reel:{str(auto_reel).lower()}}};
const ICON={{poster:'🎨',reel:'🎬'}};
function stageBase(kind){{return 'cst-stage'+(kind==='reel'?' is-reel':'');}}
function setEmpty(stage,kind,head,sub){{
  stage.className=stageBase(kind);
  stage.innerHTML='<div class="cst-empty">'+ICON[kind]+'<span>'+head+'</span><small>'+sub+'</small></div>';
}}
function gen(kind){{
  const btn=document.getElementById(kind+'-btn'),log=document.getElementById(kind+'-log'),
        stage=document.getElementById(kind+'-stage');
  btn.disabled=true;btn.textContent='Generating…';log.style.display='block';log.textContent='';
  stage.className=stageBase(kind)+' is-gen';
  stage.innerHTML='<div class="cst-empty">'+ICON[kind]+'<span>Generating your '+kind+'…</span><small>'
    +(kind==='reel'?'this usually takes 10–20 minutes (Veo) — you can leave it running':'this can take a minute')+'</small></div>';
  const es=new EventSource('/generate/'+kind+'?slug='+encodeURIComponent(SLUG));
  const line=(t,cls)=>{{const d=document.createElement('div');if(cls)d.className=cls;d.textContent=t;
    log.appendChild(d);log.scrollTop=log.scrollHeight;}};
  es.addEventListener('stage',e=>{{const d=JSON.parse(e.data);
    line(d.msg, d.msg.includes('[OK]')?'l-ok':d.msg.includes('[X]')?'l-bad':'l-run');}});
  es.addEventListener('done',e=>{{const d=JSON.parse(e.data);es.close();btn.disabled=false;btn.textContent='Regenerate';
    const u=d.asset+'&v='+Date.now();
    stage.className=stageBase(kind)+' has-asset';
    stage.innerHTML=(kind==='poster')?'<img src="'+u+'" alt="poster">'
      :'<video src="'+u+'" controls playsinline preload="metadata"></video>';
  }});
  es.addEventListener('failed',e=>{{const d=JSON.parse(e.data);es.close();btn.disabled=false;btn.textContent='Regenerate';
    line('[X] '+(d.msg||'generation failed'),'l-bad');
    setEmpty(stage,kind,'Couldn\\'t generate the '+kind,'press Regenerate to try again');}});
  es.onerror=()=>{{if(es.readyState===EventSource.CLOSED){{btn.disabled=false;}}}};
}}
// Auto-RUN what isn't made yet, right after Analyze — the studio fills itself in; Regenerate stays.
window.addEventListener('load',()=>{{
  if(AUTO.poster)gen('poster');
  if(AUTO.reel)setTimeout(()=>gen('reel'),500);   // stagger so both logs start clean
}});
</script>"""


def _studio_page(slug: str, out_dir: str) -> str | None:
    P = _run_mod.paths(slug, out_dir)
    if not P["result"].is_file():
        return None
    report = build_dashboard_html(
        str(P["result"]),
        profile_path=str(P["profile"]) if P["profile"].is_file() else None,
        plan_path=str(P["plan"]) if P["plan"].is_file() else None,
        standalone=False,           # body + CSS only — we wrap it ourselves
    )
    has_poster, has_reel = P["poster"].is_file(), P["reel"].is_file()
    section = _studio_section(slug, has_poster, has_reel)
    # inject the Creative Studio just before the report's footer (where the static creative was)
    marker = '<div class="foot"'
    i = report.rfind(marker)
    body = (report[:i] + f'<div class="bsr"><div class="wrap">{section}</div></div>' + report[i:]
            if i >= 0 else report + section)
    bar = ('<div class="cst-bar"><a href="/dashboard?slug=' + slug +
           '" target="_blank">⤓ Download the full dashboard</a></div>')
    # Auto-run the FAST poster only; the reel (10–20 min Veo) is opt-in via its button so the owner
    # never lands on a 25-minute wait they didn't ask for (proactive audit finding).
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Baseera Studio · {slug}</title>{_studio_css()}</head><body>'
            f'{bar}{body}{_studio_js(slug, not has_poster, False)}</body></html>')


# ------------------------------------------------------------------------------------------------
# HTTP handler
# ------------------------------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    out_dir: str = "outputs"
    server_version = "BaseeraStudio/2.0"

    def log_message(self, *a):
        return

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionError):
            pass

    def _begin_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")   # no keep-alive: the stream terminates
        self.end_headers()

    def _sse_write(self, frame: bytes) -> bool:
        try:
            self.wfile.write(frame)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionError, OSError):
            return False

    def do_GET(self):
        parsed = urlparse(self.path)
        route, q = parsed.path, parse_qs(parsed.query)
        if route in ("/", "/index.html"):
            self._send(200, _landing_html().encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/analyze":
            self._stream_analyze(q)
        elif route == "/studio":
            self._serve_studio(q)
        elif route == "/generate/poster":
            self._stream_generate(q, "poster")
        elif route == "/generate/reel":
            self._stream_generate(q, "reel")
        elif route == "/asset":
            self._serve_asset(q)
        elif route == "/dashboard":
            self._serve_dashboard(q)
        elif route == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    # ---- pages ----
    def _serve_studio(self, q: dict):
        slug = (q.get("slug") or [""])[0]
        if not _ok_slug(slug):
            self._send(400, b"bad slug", "text/plain; charset=utf-8")
            return
        page = _studio_page(slug, self.out_dir)
        if page is None:
            self._send(404, b"no analysis for that brand yet - run Analyze first",
                       "text/plain; charset=utf-8")
            return
        self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")

    def _serve_dashboard(self, q: dict):
        """Build + serve the full self-contained dashboard (with whatever assets exist) for export."""
        slug = (q.get("slug") or [""])[0]
        if not _ok_slug(slug):
            self._send(400, b"bad slug", "text/plain; charset=utf-8")
            return
        P = _run_mod.paths(slug, self.out_dir)
        if not P["result"].is_file():
            self._send(404, b"no analysis for that brand yet", "text/plain; charset=utf-8")
            return
        html = build_dashboard_html(
            str(P["result"]),
            profile_path=str(P["profile"]) if P["profile"].is_file() else None,
            plan_path=str(P["plan"]) if P["plan"].is_file() else None,
            poster_path=str(P["poster"]) if P["poster"].is_file() else None,
            reel_path=str(P["reel"]) if P["reel"].is_file() else None,
            standalone=True,
        )
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _serve_asset(self, q: dict):
        slug = (q.get("slug") or [""])[0]
        kind = (q.get("kind") or [""])[0]
        if not _ok_slug(slug) or kind not in ("poster", "reel"):
            self._send(400, b"bad request", "text/plain; charset=utf-8")
            return
        P = _run_mod.paths(slug, self.out_dir)
        path = P[kind]
        if not path.is_file():
            self._send(404, b"asset not generated yet", "text/plain; charset=utf-8")
            return
        ctype = "image/png" if kind == "poster" else "video/mp4"
        self._serve_file(path, ctype)

    def _serve_file(self, path: Path, ctype: str):
        try:
            data = path.read_bytes()
        except (OSError, PermissionError):
            # e.g. Windows holds an exclusive lock while ffmpeg rewrites the mp4 mid-regenerate —
            # return a clean 503 instead of letting the read escape do_GET as an unhandled 500.
            self._send(503, b"asset is being regenerated - try again in a moment",
                       "text/plain; charset=utf-8")
            return
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):     # minimal single-range (video seeking)
            try:
                start_s, end_s = rng[6:].split("-", 1)
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else len(data) - 1
                end = min(end, len(data) - 1)
                if 0 <= start <= end:
                    chunk = data[start:end + 1]
                    self._send(206, chunk, ctype, {
                        "Content-Range": f"bytes {start}-{end}/{len(data)}",
                        "Accept-Ranges": "bytes",
                    })
                    return
            except (ValueError, IndexError):
                pass
        self._send(200, data, ctype, {"Accept-Ranges": "bytes"})

    # ---- streaming pipeline stages ----
    def _stream_analyze(self, q: dict):
        url = (q.get("url") or [""])[0].strip()
        self._begin_sse()
        if not (url.startswith("http://") or url.startswith("https://")):
            self._sse_write(sse("failed", {"msg": "Enter a full URL starting with http:// or https://"}))
            return
        alive = {"v": True}

        def on_progress(event, label, msg):
            if alive["v"] and not self._sse_write(sse("stage", {"event": event, "label": label, "msg": msg})):
                alive["v"] = False

        try:
            slug = _run_mod.analyze(url, out_dir=self.out_dir, on_progress=on_progress)
        except Exception as exc:
            self._sse_write(sse("failed", {"msg": f"{type(exc).__name__}: {exc}"}))
            return
        if not alive["v"]:
            return
        if slug:
            self._sse_write(sse("done", {"slug": slug}))
        else:
            self._sse_write(sse("failed", {"msg": "The site may block scraping or be unreachable."}))

    def _stream_generate(self, q: dict, kind: str):
        slug = (q.get("slug") or [""])[0]
        self._begin_sse()
        if not _ok_slug(slug):
            self._sse_write(sse("failed", {"msg": "bad slug"}))
            return
        alive = {"v": True}

        def on_progress(event, label, msg):
            if alive["v"] and not self._sse_write(sse("stage", {"event": event, "label": label, "msg": msg})):
                alive["v"] = False

        # One generation per (slug, kind) at a time. A browser refresh / second tab / SSE reconnect
        # would otherwise spawn a DUPLICATE subprocess writing the SAME file — a torn PNG/MP4 and a
        # wasted paid Veo render. Reject the duplicate cleanly instead.
        key = (slug, kind)
        with _INFLIGHT_LOCK:
            if key in _INFLIGHT:
                self._sse_write(sse("failed",
                    {"msg": f"A {kind} is already generating for this brand — please wait for it."}))
                return
            _INFLIGHT.add(key)
        try:
            fn = _run_mod.generate_poster if kind == "poster" else _run_mod.generate_reel
            try:
                asset = fn(slug, out_dir=self.out_dir, on_progress=on_progress)
            except Exception as exc:
                self._sse_write(sse("failed", {"msg": f"{type(exc).__name__}: {exc}"}))
                return
            if not alive["v"]:
                return
            if asset and Path(asset).is_file():
                self._sse_write(sse("done", {"kind": kind, "asset": f"/asset?slug={slug}&kind={kind}"}))
            else:
                self._sse_write(sse("failed", {"msg": f"{kind} generation did not produce a file."}))
        finally:
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(key)


def serve(host: str = "127.0.0.1", port: int = 8770, out_dir: str = "outputs",
          open_browser: bool = True) -> None:
    _Handler.out_dir = out_dir
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.daemon_threads = True
    urlstr = f"http://{host}:{port}"
    print(f"\n  Baseera Studio is live -> {urlstr}\n  (Ctrl+C to stop)\n", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(urlstr)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Baseera Studio stopped.", flush=True)
    finally:
        httpd.server_close()


def main() -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="dashboard.server", description="Local interactive Baseera studio.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--out", default="outputs", help="where run artifacts are written")
    ap.add_argument("--no-open", action="store_true", help="don't auto-open the browser")
    args = ap.parse_args()
    serve(host=args.host, port=args.port, out_dir=args.out, open_browser=not args.no_open)
    return 0


if __name__ == "__main__":
    sys.exit(main())
