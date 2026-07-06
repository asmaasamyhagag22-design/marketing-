"""One-command demo: a URL in, a finished Baseera dashboard out.

    python -m dashboard.run https://brand.com            # full run (adds the one-shot poster)
    python -m dashboard.run https://brand.com --fast     # skip the poster (fastest, for a live demo)
    python -m dashboard.run https://brand.com --open      # open the dashboard when done

Runs the REAL pipeline end to end - competitor.full_run (scrape -> profile -> competitors -> SWOT
-> TOWS) -> strategy (content calendar) -> poster (one-shot, crisp logo) -> dashboard - driving the
existing tested CLIs as subprocesses so each loads .env and handles its own errors. Prints a
clean stage-by-stage progress log so it reads well when demoed live. Every stage is best-effort:
a stage that fails is skipped and the dashboard is still built from whatever succeeded.
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
    return "".join(ch if ch.isalnum() else "_" for ch in host).strip("_") or "brand"


def _run(cmd: list[str], *, timeout: int, label: str) -> tuple[bool, str]:
    """Run one stage; stream a compact status. Returns (ok, tail_of_output)."""
    print(f"  -> {label} ...", flush=True)
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        print(f"    [X] {label} timed out after {timeout}s", flush=True)
        return False, ""
    dt = time.monotonic() - t0
    tail = "\n".join((p.stdout or "").strip().splitlines()[-3:])
    if p.returncode == 0:
        print(f"    [OK] {label}  ({dt:.0f}s)", flush=True)
        return True, tail
    err = "\n".join((p.stderr or p.stdout or "").strip().splitlines()[-3:])
    print(f"    [X] {label} failed ({dt:.0f}s): {err[:200]}", flush=True)
    return False, tail


def run_pipeline(url: str, *, fast: bool = False, out_dir: str = "outputs",
                 open_when_done: bool = False) -> Path | None:
    py = sys.executable
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    slug = _slug(url)
    result_json = out / f"{slug}_result.json"
    profile_json = out / f"{slug}_profile.json"
    plan_json = out / f"{slug}_plan.json"
    poster_png = out / "posters" / f"{slug}_poster.png"
    dash_html = out / f"{slug}_dashboard.html"

    print(f"\n* Baseera - analyzing {url}\n")

    # 1) Scrape -> profile -> competitors -> SWOT -> TOWS (one command; --no-themes = faster).
    ok, _ = _run([py, "competitor/full_run.py", url, "--out", str(result_json), "--no-themes"],
                 timeout=900, label="Scrape + Profile + Competitors + SWOT")
    if not ok or not result_json.is_file():
        print("\n[X] analysis failed - cannot build a dashboard without the core result.")
        return None

    # 2) Pull the business profile out of the result so strategy/poster can reuse it (no re-scrape).
    try:
        prof = (json.loads(result_json.read_text(encoding="utf-8")).get("profile") or {})
        profile_json.write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
        have_profile = bool(prof)
    except Exception:
        have_profile = False

    # 3) Content calendar (14 days).
    if have_profile:
        _run([py, "-m", "strategy", str(profile_json), "--days", "14", "--out", str(plan_json)],
             timeout=300, label="Content calendar")

    # 4) Poster (one-shot = crisp logo). Skipped in --fast for a snappy live demo.
    poster_arg: list[str] = []
    if not fast and have_profile:
        ok, _ = _run([py, "-m", "poster", str(profile_json), "--engine", "oneshot",
                      "--out", str(poster_png), "--research"],
                     timeout=420, label="Poster (one-shot)")
        if ok and poster_png.is_file():
            poster_arg = ["--poster", str(poster_png)]

    # 5) Build the dashboard from whatever succeeded.
    cmd = [py, "-m", "dashboard", str(result_json), "--out", str(dash_html)]
    if profile_json.is_file():
        cmd += ["--profile", str(profile_json)]
    if plan_json.is_file():
        cmd += ["--plan", str(plan_json)]
    cmd += poster_arg
    ok, _ = _run(cmd, timeout=120, label="Dashboard")
    if not ok or not dash_html.is_file():
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
