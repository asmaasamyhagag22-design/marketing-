"""Benchmark harness runner.

Orchestrates the full benchmark loop:

  1. Load URL list from benchmark/urls.json
  2. For each URL:
     a. (existing-manifest mode) Find the latest scrape directory matching
        the URL's domain. Read its manifest.json + business_profile.json.
     b. (fresh-scrape mode, --scrape-fresh) Run `python -m scraper <url>`
        then `python -m business_profile <manifest>` as subprocesses.
  3. Grade each profile against URL metadata + ground truth.
  4. Aggregate per-vertical, per-tier, per-field.
  5. Write results.json + report.md to benchmark/runs/<timestamp>/.
  6. Print pass/fail verdict to stdout.

Usage:
    python -m benchmark.runner                          # existing-manifest mode (default)
    python -m benchmark.runner --scrape-fresh           # re-scrape all 13 URLs
    python -m benchmark.runner --scrape-fresh-missing   # only scrape URLs without an existing manifest
    python -m benchmark.runner --only buffalo_burger    # single-URL run for debugging
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from business_profile.schemas import BusinessProfile
from scraper.url_utils import get_domain_slug

from .graders import grade_profile, UrlGradeSet
from .report import aggregate, write_report_md, write_results_json


logger = logging.getLogger("benchmark.runner")


# ---------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = REPO_ROOT / "benchmark"
SCRAPES_DIR = REPO_ROOT / "scrapes"


def load_urls() -> dict:
    """Read benchmark/urls.json."""
    path = BENCHMARK_DIR / "urls.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_ground_truth() -> dict:
    """Read benchmark/ground_truth.json. Strip metadata-only keys."""
    path = BENCHMARK_DIR / "ground_truth.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Strip _doc / _fuzzy_fields / _format keys
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def find_latest_scrape_dir(url: str) -> Optional[Path]:
    """Return the most recent scrape output directory for a URL's domain.

    Scrape directories are named `{domain_slug}_{YYYYMMDD_HHMMSS}`.
    We pick the one with the latest timestamp suffix.
    """
    if not SCRAPES_DIR.exists():
        return None
    slug = get_domain_slug(url)
    matches = sorted(
        [p for p in SCRAPES_DIR.iterdir() if p.is_dir() and p.name.startswith(slug + "_")],
        key=lambda p: p.name,
    )
    return matches[-1] if matches else None


# ---------------------------------------------------------------------
# Subprocess invocations (fresh-scrape mode)
# ---------------------------------------------------------------------

def _utf8_env() -> dict:
    """Return an env dict with PYTHONIOENCODING=utf-8 set, so subprocess
    children don't default to cp1252 on Windows when stdout contains
    Unicode (Arabic profile summaries, em-dashes, etc.).

    2026-06 PR-D / D2: without this, the child process crashes with
    UnicodeEncodeError when rich tries to render the profile table to
    a cp1252-encoded pipe on Windows. The actual extraction succeeded;
    only the final print failed.
    """
    import os
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_scrape(url: str) -> Path:
    """Run `python -m scraper <url>` as a subprocess. Return the scrape dir."""
    logger.info(f"Scraping {url} ...")
    result = subprocess.run(
        [sys.executable, "-m", "scraper", url, "--output-dir", str(SCRAPES_DIR)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_utf8_env(),
        timeout=300,  # 5 minutes per URL max
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Scraper failed for {url}:\nstdout={result.stdout[-2000:]!r}\n"
            f"stderr={result.stderr[-2000:]!r}"
        )
    scrape_dir = find_latest_scrape_dir(url)
    if scrape_dir is None:
        raise RuntimeError(f"Scraper produced no output dir for {url}")
    logger.info(f"Scrape complete: {scrape_dir.name}")
    return scrape_dir


class QuotaExhausted(Exception):
    """Raised when extraction fails specifically because the LLM provider
    returned an insufficient-quota / 429 error. Distinct from a generic
    crash so the runner can stop gracefully and still grade the URLs that
    completed before the budget ran out, rather than churning through the
    rest and failing each one."""


def _looks_like_quota_error(text: str) -> bool:
    """Heuristic: does this subprocess output indicate an LLM quota/429?"""
    if not text:
        return False
    lowered = text.lower()
    signals = (
        "insufficient_quota",
        "exceeded your current quota",
        "429 too many requests",
        "error code: 429",
    )
    return any(s in lowered for s in signals)


def run_extract(manifest_path: Path) -> None:
    """Run `python -m business_profile <manifest>` to produce business_profile.json.

    IMPORTANT: `business_profile` exits with code 2 when the profile is built
    successfully but is NOT "ready_for_strategy" (a deliberate signal for
    interactive/scripting use). That is NOT an extraction failure — the
    profile JSON is written to disk and is fully gradeable. So we do NOT
    treat a non-zero exit code as failure on its own; instead we check
    whether the profile file was actually produced (done by the caller).

    We still raise:
      - QuotaExhausted if the output shows an LLM quota/429 error
      - RuntimeError only for a genuine crash (handled by the caller when
        the expected profile file is missing after this returns)
    """
    profile_path = manifest_path.parent / "business_profile.json"
    logger.info(f"Extracting profile from {manifest_path.parent.name} ...")
    result = subprocess.run(
        [sys.executable, "-m", "business_profile", str(manifest_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_utf8_env(),
        timeout=600,  # 10 minutes — LLM calls can be slow
    )

    # Quota errors are detected regardless of exit code / file state.
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    if _looks_like_quota_error(combined):
        raise QuotaExhausted(
            "LLM provider returned insufficient_quota / 429. "
            "Top up the API account (or switch keys) and re-run."
        )

    # exit code 2 == "profile built but not ready_for_strategy" (NOT a crash).
    # Any non-zero exit is only a real failure if NO profile file was
    # written. If the file exists, extraction succeeded and we grade it.
    if result.returncode != 0 and not profile_path.exists():
        raise RuntimeError(
            f"Extraction failed (exit {result.returncode}, no profile written):\n"
            f"stdout={result.stdout[-2000:]!r}\n"
            f"stderr={result.stderr[-2000:]!r}"
        )
    # else: returncode 0 (ready) OR returncode 2 with a written profile —
    # both are successful extractions. The caller verifies the file exists.


# ---------------------------------------------------------------------
# Per-URL evaluation
# ---------------------------------------------------------------------

def _manifest_is_bot_blocked(manifest_path: Path) -> bool:
    """Return True ONLY if the scrape was blocked COMPLETELY by bot
    protection — i.e. the site yielded no extractable content at all.

    The distinction matters and was a real bug: a site can emit a
    BOT_PROTECTION failure for SOME pages while still successfully
    scraping others. Example:
      - Mumm:        pages_succeeded=0, text_blocks=0, BOT_PROTECTION
                     -> genuinely blocked, exclude.
      - Raw African: pages_succeeded=4, text_blocks=507, BOT_PROTECTION
                     -> some pages blocked but 507 blocks extracted;
                        the scraper SUCCEEDED. Do NOT exclude — grade it.

    So presence of a BOT_PROTECTION code is necessary but NOT sufficient.
    We exclude only when the block left us with zero usable content:
    no successful pages AND no text blocks. That keeps the exclusion
    narrow (only truly unreachable sites) and prevents it from hiding a
    site the scraper actually handled.
    """
    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    failures = m.get("failures") or []
    has_bot_protection = any(
        isinstance(f, dict) and f.get("code") == "BOT_PROTECTION"
        for f in failures
    )
    if not has_bot_protection:
        return False

    # Bot protection is present — but did the scrape still yield content?
    pages_succeeded = (m.get("scrape_meta") or {}).get("pages_succeeded", 0)
    text_block_count = sum(
        len(p.get("text_blocks") or []) for p in (m.get("pages") or [])
    )

    # Exclude ONLY if the site was blocked completely (no content at all).
    return pages_succeeded == 0 and text_block_count == 0


def evaluate_url(
    url_meta: dict,
    ground_truth: dict,
    mode: str,
) -> tuple[Optional[UrlGradeSet], Optional[str]]:
    """Evaluate one URL. Returns (grade_set, error_message).
    On failure, grade_set is None and error_message describes what went wrong.

    Special case: if extraction fails due to LLM quota exhaustion, the
    error_message is prefixed with "QUOTA:" so the main loop can stop the
    run gracefully (grading what completed) instead of churning through
    every remaining URL and failing each one identically.
    """
    url = url_meta["url"]
    url_id = url_meta["id"]

    # 1. Resolve scrape directory
    scrape_dir = find_latest_scrape_dir(url)

    if mode in ("fresh", "fresh-missing"):
        need_scrape = (mode == "fresh") or scrape_dir is None
        if need_scrape:
            try:
                scrape_dir = run_scrape(url)
            except Exception as e:
                return None, f"scrape failed: {e}"

    if scrape_dir is None:
        return None, f"no scrape directory found for {url} (try --scrape-fresh)"

    manifest_path = scrape_dir / "manifest.json"
    profile_path = scrape_dir / "business_profile.json"

    if not manifest_path.exists():
        return None, f"missing manifest at {manifest_path}"

    # Bot-protected sites are excluded from scoring (not failed, not graded).
    # The scraper did its job and correctly reported the block; there is no
    # reachable content to extract, so a 0.0 would unfairly penalize the
    # scraper for the site's anti-bot system. Signal with EXCLUDED: prefix.
    if _manifest_is_bot_blocked(manifest_path):
        return None, "EXCLUDED: site blocked access (bot protection)"

    # 2. Run extraction if profile doesn't exist (or fresh-scrape forces refresh)
    if not profile_path.exists() or mode == "fresh":
        try:
            run_extract(manifest_path)
        except QuotaExhausted as e:
            # Signal to the main loop with a recognizable prefix so it can
            # stop the run rather than failing every remaining URL.
            return None, f"QUOTA: {e}"
        except Exception as e:
            return None, f"extraction failed: {e}"

    if not profile_path.exists():
        return None, f"extraction did not produce profile at {profile_path}"

    # 3. Load profile and grade
    try:
        profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
        profile = BusinessProfile.model_validate(profile_data)
    except Exception as e:
        return None, f"profile load failed: {e}"

    try:
        grade_set = grade_profile(profile, url_meta, ground_truth)
    except Exception as e:
        return None, f"grading failed: {e}"

    return grade_set, None


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run the scraper benchmark")
    parser.add_argument(
        "--scrape-fresh", action="store_true",
        help="Re-scrape every URL (expensive: LLM costs + ~5 min per URL)",
    )
    parser.add_argument(
        "--scrape-fresh-missing", action="store_true",
        help="Only scrape URLs without an existing manifest",
    )
    parser.add_argument(
        "--only", type=str, default=None,
        help="Run only the URL with this id (e.g. 'buffalo_burger'). Useful for debugging.",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Where to write run output (default: benchmark/runs/<timestamp>/)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Mode resolution
    if args.scrape_fresh:
        mode = "fresh"
    elif args.scrape_fresh_missing:
        mode = "fresh-missing"
    else:
        mode = "existing"

    # Load inputs
    urls_data = load_urls()
    ground_truth = load_ground_truth()
    thresholds = urls_data["thresholds"]
    url_list = urls_data["urls"]

    if args.only:
        url_list = [u for u in url_list if u["id"] == args.only]
        if not url_list:
            sys.exit(f"No URL with id {args.only!r}")

    # Resolve output dir
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = BENCHMARK_DIR / "runs" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    # Evaluate
    grade_sets: list[UrlGradeSet] = []
    errors: dict[str, str] = {}
    excluded: dict[str, str] = {}
    quota_hit = False
    for url_meta in url_list:
        print(f"\n--- {url_meta['id']} ({url_meta['brand']}) ---")
        gs, err = evaluate_url(url_meta, ground_truth, mode)
        if err:
            if err.startswith("QUOTA:"):
                # LLM budget ran out. Stop here rather than failing every
                # remaining URL identically. Grade what we have so far.
                quota_hit = True
                print(f"  QUOTA EXHAUSTED: {err[len('QUOTA: '):]}")
                print(f"  Stopping the run. {len(grade_sets)} URL(s) graded "
                      f"before quota ran out; {len(url_list) - len(grade_sets) - len(errors)} "
                      f"URL(s) not attempted.")
                break
            if err.startswith("EXCLUDED:"):
                # Site blocked access (bot protection). Not a failure and
                # not graded — excluded from all averages. The scraper
                # behaved correctly; there's simply no content to score.
                excluded[url_meta["id"]] = err[len("EXCLUDED: "):]
                print(f"  EXCLUDED: {err[len('EXCLUDED: '):]}")
                continue
            errors[url_meta["id"]] = err
            print(f"  ERROR: {err}")
            continue
        print(f"  graded: avg_swot={gs.avg_score(only_swot_critical=True)}, "
              f"avg_all={gs.avg_score()}")
        grade_sets.append(gs)

    if not grade_sets:
        sys.exit("\nNo URLs graded successfully. Aborting report.")

    # Aggregate + write
    url_metadata_by_id = {u["id"]: u for u in url_list}
    aggregations = aggregate(grade_sets, url_metadata_by_id, thresholds)

    run_meta = {
        "timestamp": timestamp,
        "url_count": len(grade_sets),
        "mode": mode,
        "grid_version": urls_data.get("grid_version"),
        "grid_locked_at": urls_data.get("locked_at"),
        "errors": errors,
        "excluded": excluded,
        "quota_exhausted": quota_hit,
        "urls_total": len(url_list),
    }

    write_results_json(grade_sets, aggregations, run_meta, out_dir / "results.json")
    write_report_md(grade_sets, aggregations, run_meta, out_dir / "report.md")

    # Verdict
    # An errored URL counts as a benchmark failure even if the URLs that
    # DID grade hit threshold. Otherwise "1 perfect URL + 13 errors" would
    # falsely report PASS. Failing closed is the safer default. A
    # quota-truncated run also cannot pass — it's an incomplete measurement.
    #
    # EXCLUDED URLs (bot-protected sites) are NOT incomplete: they are
    # legitimately accounted for. A run where every URL is either graded
    # or explicitly excluded is complete. We only require that at least
    # one URL graded, and that there are no hard errors / no quota cutoff.
    tc = aggregations["threshold_check"]
    accounted = len(grade_sets) + len(excluded)
    incomplete = bool(errors) or quota_hit or accounted < len(url_list)
    passed = tc["passed"] and not incomplete
    print("\n" + "=" * 60)
    if passed:
        print("THRESHOLD CHECK: PASS")
    else:
        print("THRESHOLD CHECK: FAIL")
        for f in tc["failures"]:
            print(f"  - {f}")
        if quota_hit:
            print(f"  - run truncated by LLM quota exhaustion: "
                  f"only {len(grade_sets)}/{len(url_list)} URLs graded "
                  f"(top up the API account and re-run for a complete measurement)")
        if errors:
            print(f"  - {len(errors)}/{len(url_list)} URLs errored "
                  f"(cannot pass with partial results)")
    if excluded:
        print(f"\n{len(excluded)} URL(s) excluded from scoring (site blocked access):")
        for url_id, msg in excluded.items():
            print(f"  {url_id}: {msg}")
    print(f"\nResults: {out_dir}/results.json")
    print(f"Report:  {out_dir}/report.md")
    if errors:
        print(f"\n{len(errors)} URL(s) errored:")
        for url_id, msg in errors.items():
            print(f"  {url_id}: {msg[:80]}")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()