"""Baseera - a LOCAL live web app for the whole pipeline.

    python -m dashboard.server              # -> http://127.0.0.1:8770  (opens the browser)
    python -m dashboard.server --port 9000 --no-open

Open it, paste a business URL, press Analyze, and WATCH the pipeline run live (scrape -> profile
-> competitors -> SWOT -> TOWS -> calendar -> poster -> dashboard). Progress streams over SSE so
each stage lights up as it finishes; when it's done the finished Baseera dashboard opens inline.

Deliberately stdlib-only (http.server + threads): no framework, no async, no build step - it just
runs. The heavy lifting is the SAME tested pipeline as `python -m dashboard.run`; this only wraps a
thin live UI around it. Every run is best-effort (a failed stage is skipped, the dashboard is still
built from whatever succeeded), exactly like the CLI.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dashboard import run as _run_mod

# Baseera palette (kept in lock-step with dashboard/build.py::_C so the landing page and the
# dashboard it produces read as one product).
_C = {
    "bg": "#FAF5F1", "surface": "#FFFFFF", "ink": "#2A1A1F", "inkSoft": "#5C4A52",
    "muted": "#9B8A92", "line": "rgba(168,69,107,0.14)",
    "blush100": "#F6E0E7", "blush500": "#B85C7A", "blush600": "#9C4564", "blush700": "#7E3450",
    "ok": "#3F8F6B", "bad": "#B54848", "gold": "#C68A3C",
}


def sse(event: str, data) -> bytes:
    """Format one Server-Sent Event frame. Pure + testable: `data` is JSON-encoded so newlines
    in a progress line can never break the `data:` framing."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def _safe_out_file(out_dir: Path, name: str) -> Path | None:
    """Resolve `name` strictly inside out_dir (blocks ../ traversal); only .html is served."""
    if not name or not name.endswith(".html"):
        return None
    p = (out_dir / name).resolve()
    try:
        p.relative_to(out_dir.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


def _landing_html() -> str:
    c = _C
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Baseera - Marketing Intelligence</title>
<style>
  :root{{color-scheme:light;}}
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{
    font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
    color:{c['ink']};background:{c['bg']};line-height:1.5;-webkit-font-smoothing:antialiased;
    background-image:
      radial-gradient(circle at 8% 4%,rgba(236,203,214,.38) 0%,transparent 26%),
      radial-gradient(circle at 94% 8%,rgba(240,228,211,.30) 0%,transparent 28%),
      radial-gradient(circle at 96% 96%,rgba(221,168,185,.22) 0%,transparent 30%),
      radial-gradient(circle at 4% 98%,rgba(246,224,231,.36) 0%,transparent 28%);
    min-height:100vh;padding:34px clamp(14px,4vw,44px) 60px;
  }}
  .serif{{font-family:'Fraunces',Georgia,'Times New Roman',serif;}}
  .wrap{{max-width:960px;margin:0 auto;}}
  .brand{{display:flex;align-items:center;gap:11px;margin-bottom:22px;}}
  .dot{{width:34px;height:34px;border-radius:11px;flex:none;
    background:linear-gradient(135deg,{c['blush500']},{c['blush700']});
    box-shadow:0 6px 16px rgba(158,69,100,.28);}}
  .brand-n{{font-family:'Fraunces',Georgia,serif;font-weight:600;font-size:22px;letter-spacing:-.3px;}}
  .brand-t{{font-size:12px;color:{c['muted']};letter-spacing:.4px;text-transform:uppercase;}}
  .card{{background:{c['surface']};border:1px solid {c['line']};border-radius:20px;
    padding:clamp(20px,4vw,34px);box-shadow:0 14px 40px rgba(126,52,80,.09);}}
  h1{{font-family:'Fraunces',Georgia,serif;font-weight:600;font-size:clamp(24px,4vw,34px);
    line-height:1.12;letter-spacing:-.6px;margin-bottom:8px;}}
  h1 em{{font-style:normal;color:{c['blush600']};}}
  .sub{{color:{c['inkSoft']};font-size:15px;max-width:60ch;margin-bottom:24px;}}
  .row{{display:flex;gap:10px;flex-wrap:wrap;}}
  input[type=url]{{flex:1 1 340px;min-width:0;padding:14px 16px;font-size:15px;
    border:1.5px solid {c['line']};border-radius:12px;background:#fff;color:{c['ink']};
    font-family:inherit;transition:border-color .15s,box-shadow .15s;}}
  input[type=url]:focus{{outline:none;border-color:{c['blush500']};
    box-shadow:0 0 0 4px rgba(184,92,122,.14);}}
  button{{padding:14px 26px;font-size:15px;font-weight:600;font-family:inherit;cursor:pointer;
    color:#fff;border:none;border-radius:12px;white-space:nowrap;
    background:linear-gradient(135deg,{c['blush500']},{c['blush700']});
    box-shadow:0 8px 20px rgba(158,69,100,.26);transition:transform .12s,box-shadow .12s,opacity .12s;}}
  button:hover:not(:disabled){{transform:translateY(-1px);box-shadow:0 12px 26px rgba(158,69,100,.32);}}
  button:disabled{{opacity:.5;cursor:not-allowed;}}
  .opts{{display:flex;align-items:center;gap:8px;margin-top:14px;font-size:13px;color:{c['inkSoft']};}}
  .opts input{{accent-color:{c['blush600']};width:15px;height:15px;}}
  /* live console */
  .stage-strip{{display:flex;flex-wrap:wrap;gap:7px;margin-top:24px;}}
  .chip{{font-size:11.5px;font-weight:600;letter-spacing:.2px;padding:6px 12px;border-radius:999px;
    background:#fff;border:1px solid {c['line']};color:{c['muted']};transition:all .2s;}}
  .chip.run{{color:{c['blush700']};border-color:{c['blush500']};background:{c['blush100']};
    animation:pulse 1.1s ease-in-out infinite;}}
  .chip.ok{{color:{c['ok']};border-color:rgba(63,143,107,.4);background:rgba(63,143,107,.09);}}
  .chip.bad{{color:{c['bad']};border-color:rgba(181,72,72,.4);background:rgba(181,72,72,.08);}}
  @keyframes pulse{{0%,100%{{opacity:1;}}50%{{opacity:.55;}}}}
  #log{{margin-top:18px;background:#2A1A1F;color:#F3E7EC;border-radius:14px;padding:16px 18px;
    font-family:'Space Grotesk',ui-monospace,'SF Mono',Menlo,Consolas,monospace;font-size:12.5px;
    line-height:1.7;max-height:320px;overflow:auto;display:none;white-space:pre-wrap;word-break:break-word;}}
  #log .l-ok{{color:#8FE0B8;}} #log .l-bad{{color:#F3A8A8;}} #log .l-run{{color:#E8C7D4;}}
  #log .l-hd{{color:{c['gold']};font-weight:700;}}
  .done{{display:none;margin-top:22px;padding:18px 20px;border-radius:14px;
    background:rgba(63,143,107,.08);border:1px solid rgba(63,143,107,.3);}}
  .done.show{{display:block;}} .done.fail{{background:rgba(181,72,72,.07);border-color:rgba(181,72,72,.3);}}
  .done h3{{font-family:'Fraunces',Georgia,serif;font-size:18px;margin-bottom:6px;}}
  .done a{{display:inline-block;margin-top:12px;color:#fff;text-decoration:none;font-weight:600;
    padding:11px 22px;border-radius:11px;background:linear-gradient(135deg,{c['blush500']},{c['blush700']});}}
  iframe{{width:100%;height:78vh;margin-top:20px;border:1px solid {c['line']};border-radius:16px;
    background:#fff;box-shadow:0 14px 40px rgba(126,52,80,.10);display:none;}}
  iframe.show{{display:block;}}
  .foot{{text-align:center;color:{c['muted']};font-size:12px;margin-top:26px;}}
</style></head><body>
<div class="wrap">
  <div class="brand">
    <div class="dot"></div>
    <div><div class="brand-n">Baseera</div><div class="brand-t">Marketing Intelligence</div></div>
  </div>
  <div class="card">
    <h1 class="serif">One URL in, a <em>full campaign</em> out.</h1>
    <p class="sub">Paste any brand's website. Baseera scrapes it, profiles the business, studies the
      competitors, builds a cited SWOT and strategy, designs a poster, and assembles a live
      dashboard - and you watch every stage happen.</p>
    <div class="row">
      <input id="url" type="url" placeholder="https://your-brand.com" autocomplete="off" spellcheck="false">
      <button id="go">Analyze</button>
    </div>
    <label class="opts"><input id="fast" type="checkbox"> Fast preview (skip the poster)</label>

    <div id="strip" class="stage-strip" style="display:none"></div>
    <div id="log"></div>
    <div id="done" class="done"><h3></h3><p></p><a target="_blank">Open dashboard</a></div>
    <iframe id="frame" title="Baseera dashboard"></iframe>
  </div>
  <div class="foot">Runs locally on your machine. Nothing leaves except the page you analyze.</div>
</div>
<script>
const STAGES = ["Scrape + Profile + Competitors + SWOT","Content calendar","Poster (one-shot)","Dashboard"];
const $=s=>document.querySelector(s);
const url=$("#url"), go=$("#go"), fast=$("#fast"), strip=$("#strip"), log=$("#log"),
      done=$("#done"), frame=$("#frame");
let es=null;

function chips(){{ strip.innerHTML=""; strip.style.display="flex";
  STAGES.forEach(s=>{{const d=document.createElement("div");d.className="chip";d.dataset.k=s;
    d.textContent=s.replace(" + Competitors + SWOT","...");strip.appendChild(d);}}); }}
function setChip(label,cls){{ const el=[...strip.children].find(c=>label.startsWith(c.dataset.k.split(" ...")[0].split(" +")[0])||c.dataset.k===label);
  if(el){{el.className="chip "+cls;}} }}
function line(txt){{ const div=document.createElement("div");
  if(txt.includes("[OK]"))div.className="l-ok"; else if(txt.includes("[X]"))div.className="l-bad";
  else if(txt.trim().startsWith("->"))div.className="l-run"; else if(txt.startsWith("*"))div.className="l-hd";
  div.textContent=txt; log.appendChild(div); log.scrollTop=log.scrollHeight; }}

go.onclick=()=>{{
  const u=url.value.trim(); if(!u){{url.focus();return;}}
  if(es)es.close();
  go.disabled=true; done.className="done"; frame.className=""; frame.src="about:blank";
  log.style.display="block"; log.innerHTML=""; chips();
  line("* Baseera - analyzing "+u+"\\n");
  es=new EventSource("/run?url="+encodeURIComponent(u)+(fast.checked?"&fast=1":""));
  es.addEventListener("stage",e=>{{ const d=JSON.parse(e.data); line(d.msg);
    if(d.event==="stage_start")setChip(d.label,"run");
    else if(d.event==="stage_ok")setChip(d.label,"ok");
    else if(d.event==="stage_fail")setChip(d.label,"bad"); }});
  es.addEventListener("done",e=>{{ const d=JSON.parse(e.data); es.close(); go.disabled=false;
    done.querySelector("h3").textContent="Your Baseera dashboard is ready.";
    done.querySelector("p").textContent="Scroll down for the full campaign, or open it in its own tab.";
    const a=done.querySelector("a"); a.href=d.view; done.className="done show";
    frame.src=d.view; frame.className="show"; frame.scrollIntoView({{behavior:"smooth"}}); }});
  es.addEventListener("failed",e=>{{ const d=JSON.parse(e.data); es.close(); go.disabled=false;
    done.querySelector("h3").textContent="That run couldn't finish.";
    done.querySelector("p").textContent=d.msg||"The site may block scraping or be unreachable.";
    done.querySelector("a").style.display="none"; done.className="done show fail"; }});
  es.onerror=()=>{{ if(es.readyState===EventSource.CLOSED){{go.disabled=false;}} }};
}};
url.addEventListener("keydown",e=>{{ if(e.key==="Enter")go.click(); }});
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    out_dir: Path = Path("outputs")
    server_version = "Baseera/1.0"

    def log_message(self, *a):  # keep the console clean; the pipeline prints its own log
        return

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionError):
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        if route in ("/", "/index.html"):
            self._send(200, _landing_html().encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/run":
            self._stream_run(parse_qs(parsed.query))
        elif route == "/view":
            self._serve_view(parse_qs(parsed.query))
        elif route == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def _serve_view(self, q: dict):
        name = (q.get("f") or [""])[0]
        p = _safe_out_file(self.out_dir, name)
        if not p:
            self._send(404, b"dashboard not found", "text/plain; charset=utf-8")
            return
        self._send(200, p.read_bytes(), "text/html; charset=utf-8")

    def _sse_write(self, frame: bytes) -> bool:
        try:
            self.wfile.write(frame)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionError, OSError):
            return False

    def _stream_run(self, q: dict):
        url = (q.get("url") or [""])[0].strip()
        fast = bool(q.get("fast"))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        # No keep-alive: this stream terminates. Advertising keep-alive makes http.server hold the
        # socket open, so the browser (and tests) would hang waiting for a next request instead of
        # seeing the stream end. HTTP/1.0's close-on-return is exactly what SSE-with-a-finish wants.
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        if not (url.startswith("http://") or url.startswith("https://")):
            self._sse_write(sse("failed", {"msg": "Enter a full URL starting with http:// or https://"}))
            return

        alive = {"v": True}

        def on_progress(event, label, msg):
            if not alive["v"]:
                return
            if not self._sse_write(sse("stage", {"event": event, "label": label, "msg": msg})):
                alive["v"] = False

        try:
            dash = _run_mod.run_pipeline(url, fast=fast, out_dir=str(self.out_dir),
                                         open_when_done=False, on_progress=on_progress)
        except Exception as exc:  # a crash in a stage must not kill the whole server
            self._sse_write(sse("failed", {"msg": f"{type(exc).__name__}: {exc}"}))
            return

        if not alive["v"]:
            return
        if dash and Path(dash).is_file():
            self._sse_write(sse("done", {"view": f"/view?f={Path(dash).name}"}))
        else:
            self._sse_write(sse("failed",
                {"msg": "The analysis couldn't produce a dashboard - the site may block scraping."}))


def serve(host: str = "127.0.0.1", port: int = 8770, out_dir: str = "outputs",
          open_browser: bool = True) -> None:
    _Handler.out_dir = Path(out_dir)
    _Handler.out_dir.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.daemon_threads = True
    urlstr = f"http://{host}:{port}"
    print(f"\n  Baseera is live -> {urlstr}\n  (Ctrl+C to stop)\n", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(urlstr)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Baseera stopped.", flush=True)
    finally:
        httpd.server_close()


def main() -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="dashboard.server", description="Local live Baseera web app.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--out", default="outputs", help="where run artifacts are written")
    ap.add_argument("--no-open", action="store_true", help="don't auto-open the browser")
    args = ap.parse_args()
    serve(host=args.host, port=args.port, out_dir=args.out, open_browser=not args.no_open)
    return 0


if __name__ == "__main__":
    sys.exit(main())
