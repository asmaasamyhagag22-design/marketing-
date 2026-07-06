"""CLI: python -m dashboard <competitor_result.json> [--profile p.json] [--plan plan.json]
                          [--poster poster.png] [--out dashboard.html] [--artifact]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .build import build_dashboard


def main() -> int:
    ap = argparse.ArgumentParser(prog="dashboard", description="Build the Baseera brand dashboard.")
    ap.add_argument("competitor", nargs="?", help="a competitor.full_run result.json (SWOT/TOWS/peers)")
    ap.add_argument("--profile", default=None, help="a business_profile.json")
    ap.add_argument("--plan", default=None, help="a content_plan.json (from python -m strategy)")
    ap.add_argument("--poster", default=None, help="a rendered poster PNG to embed")
    ap.add_argument("--out", default="outputs/dashboard.html", help="output HTML path")
    ap.add_argument("--artifact", action="store_true",
                    help="emit body+style only (no <html>/<head>) for publishing as an Artifact")
    args = ap.parse_args()

    out = build_dashboard(
        args.competitor, profile_path=args.profile, plan_path=args.plan,
        poster_path=args.poster, out_path=args.out, standalone=not args.artifact,
    )
    print(f"[dashboard] -> {out}  ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
