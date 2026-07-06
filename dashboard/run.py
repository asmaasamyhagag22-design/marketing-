"""One-command demo: a URL in, a finished Baseera dashboard out.

    python -m dashboard.run https://brand.com            # full run (adds the one-shot poster)
    python -m dashboard.run https://brand.com --fast     # skip the poster (fastest, for a live demo)
    python -m dashboard.run https://brand.com --open      # open the dashboard when done

Runs the REAL pipeline end to end - competitor.full_run (scrape -> profile -> competitors -> SWOT
-> TOWS) -> strategy (content calendar) -> poster (one-shot, crisp logo) -> reel (Opus-directed,
Veo 3.1) -> dashboard - driving the existing tested CLIs as subprocesses so each loads .env and
handles its own errors. The finished dashboard embeds BOTH the poster and the reel, so everything
shows in one place. Prints a clean stage-by-stage progress log so it reads well when demoed live.
Every stage is best-effort: a stage that fails is skipped and the dashboard is still built from
whatever succeeded. `--fast` skips the heavy poster + reel for a snappy preview.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

# Windows consoles default to cp1252 and choke on non-ASCII; force UTF-8 so the progress log
# (and any Arabic in stage output) never crashes a live demo.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


def _slug(url: str) -> str:
    host = (urlparse(url).netloc or url).replace("www.", "").replace(":", "_")
    # ASCII-only: str.isalnum() is True for Unicode letters (é, ü, 日), which would make a slug the
    # server's ASCII guard (_SLUG_RE) rejects — an IDN brand would analyze fine then 400 at /studio.
    # These bytes also become on-disk filenames, so keep them plain ASCII.
    return "".join(ch if (ch.isascii() and ch.isalnum()) else "_"
                   for ch in host).strip("_") or "brand"


def _emit(on_progress, event: str, label: str, msg: str) -> None:
    """Print for the CLI and, when a live UI is watching, forward (event, label, msg)."""
    print(msg, flush=True)
    if on_progress:
        try:
            on_progress(event, label, msg)
        except Exception:
            pass


def _run(cmd: list[str], *, timeout: int, label: str, on_progress=None) -> tuple[bool, str]:
    """Run one stage; stream a compact status. Returns (ok, tail_of_output)."""
    _emit(on_progress, "stage_start", label, f"  -> {label} ...")
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        _emit(on_progress, "stage_fail", label, f"    [X] {label} timed out after {timeout}s")
        return False, ""
    dt = time.monotonic() - t0
    tail = "\n".join((p.stdout or "").strip().splitlines()[-3:])
    if p.returncode == 0:
        _emit(on_progress, "stage_ok", label, f"    [OK] {label}  ({dt:.0f}s)")
        return True, tail
    err = "\n".join((p.stderr or p.stdout or "").strip().splitlines()[-3:])
    _emit(on_progress, "stage_fail", label, f"    [X] {label} failed ({dt:.0f}s): {err[:200]}")
    return False, tail


def paths(slug: str, out_dir: str = "outputs") -> dict:
    """Every artifact path for a brand slug — shared by analyze / generate_* / build so the
    interactive studio and the one-shot CLI address the exact same files."""
    out = Path(out_dir)
    return {
        "out": out, "slug": slug,
        "result": out / f"{slug}_result.json",
        "profile": out / f"{slug}_profile.json",
        "plan": out / f"{slug}_plan.json",
        "poster": out / "posters" / f"{slug}_poster.png",
        "reel": out / "reels" / f"{slug}_reel.mp4",
        "dash": out / f"{slug}_dashboard.html",
    }


def analyze(url: str, *, out_dir: str = "outputs", on_progress=None) -> str | None:
    """The FAST core: scrape -> profile -> competitors -> SWOT -> TOWS -> content calendar. No
    poster/reel (those are generated on demand from the studio). Returns the brand slug, or None
    if the core analysis failed. Writes <slug>_result/profile/plan.json into out_dir."""
    py = sys.executable
    slug = _slug(url)
    P = paths(slug, out_dir)
    P["out"].mkdir(parents=True, exist_ok=True)
    _emit(on_progress, "run_start", "Analyze", f"\n* Baseera - analyzing {url}\n")

    # 1500s (25 min): a full competitive analysis of a rich e-commerce brand (30-page crawl +
    # discovering & scraping each peer + profile LLM + SWOT) genuinely exceeded the old 900s and
    # was killed mid-run (MEASURED: rawafrican.net). The subprocess prints its own [1/5]... progress.
    ok, _ = _run([py, "competitor/full_run.py", url, "--out", str(P["result"]), "--no-themes"],
                 timeout=1500, label="Scrape + Profile + Competitors + SWOT", on_progress=on_progress)
    if not ok or not P["result"].is_file():
        return None

    try:
        prof = (json.loads(P["result"].read_text(encoding="utf-8")).get("profile") or {})
        P["profile"].write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
        have_profile = bool(prof)
    except Exception:
        have_profile = False

    if have_profile:
        _run([py, "-m", "strategy", str(P["profile"]), "--days", "14", "--out", str(P["plan"])],
             timeout=300, label="Content calendar", on_progress=on_progress)
    return slug


def _product_args(product_name: str | None, product_image: str | None) -> list[str]:
    """CLI flags so the poster/reel FEATURE the user-picked product (else whole-brand)."""
    args: list[str] = []
    if product_name:
        args += ["--product-name", product_name]
    if product_image:
        args += ["--product-image", product_image]
    return args


def generate_poster(slug: str, *, out_dir: str = "outputs", on_progress=None,
                    product_name: str | None = None, product_image: str | None = None) -> Path | None:
    """On-demand: (re)generate the one-shot poster from the saved profile, optionally FEATURING a
    picked product. Returns its path."""
    py = sys.executable
    P = paths(slug, out_dir)
    if not P["profile"].is_file():
        return None
    P["poster"].parent.mkdir(parents=True, exist_ok=True)
    # No --research on the studio path (deep web research pushed it past 420s). 900s: the one-shot
    # engine regenerates the slow image model on a QA-gate fail (bounded retries), so a legitimately
    # retrying poster needs room (MEASURED: rawafrican exceeded 600s). Still profile-grounded.
    ok, _ = _run([py, "-m", "poster", str(P["profile"]), "--engine", "oneshot",
                  "--out", str(P["poster"])] + _product_args(product_name, product_image),
                 timeout=900, label="Poster (one-shot)", on_progress=on_progress)
    return P["poster"] if (ok and P["poster"].is_file()) else None


def generate_reel(slug: str, *, out_dir: str = "outputs", on_progress=None,
                 product_name: str | None = None, product_image: str | None = None) -> Path | None:
    """On-demand: (re)generate the Opus-directed Veo 3.1 reel, optionally FEATURING a picked product."""
    py = sys.executable
    P = paths(slug, out_dir)
    if not P["profile"].is_file():
        return None
    P["reel"].parent.mkdir(parents=True, exist_ok=True)
    ok, _ = _run([py, "-m", "reel", str(P["profile"]), "--creative", "--out", str(P["reel"])]
                 + _product_args(product_name, product_image),
                 timeout=1500, label="Reel (Veo 3.1, Opus-directed)", on_progress=on_progress)
    return P["reel"] if (ok and P["reel"].is_file()) else None


def build_dashboard_file(slug: str, *, out_dir: str = "outputs", poster: Path | None = None,
                         reel: Path | None = None, on_progress=None) -> Path | None:
    """Build the self-contained dashboard HTML from whatever artifacts exist for this slug."""
    py = sys.executable
    P = paths(slug, out_dir)
    if not P["result"].is_file():
        return None
    cmd = [py, "-m", "dashboard", str(P["result"]), "--out", str(P["dash"])]
    if P["profile"].is_file():
        cmd += ["--profile", str(P["profile"])]
    if P["plan"].is_file():
        cmd += ["--plan", str(P["plan"])]
    if poster and Path(poster).is_file():
        cmd += ["--poster", str(poster)]
    if reel and Path(reel).is_file():
        cmd += ["--reel", str(reel)]
    ok, _ = _run(cmd, timeout=120, label="Dashboard", on_progress=on_progress)
    return P["dash"] if (ok and P["dash"].is_file()) else None


def run_pipeline(url: str, *, fast: bool = False, out_dir: str = "outputs",
                 open_when_done: bool = False, on_progress=None) -> Path | None:
    """One-shot CLI: URL in, a finished dashboard out (analyze -> poster -> reel -> build)."""
    slug = analyze(url, out_dir=out_dir, on_progress=on_progress)
    if not slug:
        print("\n[X] analysis failed - cannot build a dashboard without the core result.")
        return None
    poster = None if fast else generate_poster(slug, out_dir=out_dir, on_progress=on_progress)
    reel = None if fast else generate_reel(slug, out_dir=out_dir, on_progress=on_progress)
    dash_html = build_dashboard_file(slug, out_dir=out_dir, poster=poster, reel=reel,
                                     on_progress=on_progress)
    if not dash_html:
        return None
    print(f"\n[OK] DONE -> {dash_html.resolve()}")
    if open_when_done:
        try:
            webbrowser.open(dash_html.resolve().as_uri())
        except Exception:
            pass
    return dash_html


def main() -> int:
    ap = argparse.ArgumentParser(prog="dashboard.run",
                                 description="URL -> full analysis -> Baseera dashboard.")
    ap.add_argument("url", help="the brand's website URL")
    ap.add_argument("--fast", action="store_true", help="skip the poster (fastest - for a live demo)")
    ap.add_argument("--out-dir", default="outputs", help="output directory")
    ap.add_argument("--open", action="store_true", help="open the dashboard in a browser when done")
    args = ap.parse_args()
    dash = run_pipeline(args.url, fast=args.fast, out_dir=args.out_dir, open_when_done=args.open)
    return 0 if dash else 1


if __name__ == "__main__":
    raise SystemExit(main())
