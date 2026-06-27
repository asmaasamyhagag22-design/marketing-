"""CLI: fan a content calendar out into posters + reels.

    python -m campaign profile.json --from-plan content_plan.json --dry-run
    python -m campaign profile.json --from-plan content_plan.json --only 0 --trend
    python -m campaign profile.json --from-plan content_plan.json        # render ALL items
"""
from __future__ import annotations

import argparse
import functools
import json
import sys
from pathlib import Path


def main() -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass

    ap = argparse.ArgumentParser(prog="campaign", description="Calendar -> posters + reels.")
    ap.add_argument("profile", help="path to a business_profile.json")
    ap.add_argument("--from-plan", required=True, help="content_plan.json from `python -m strategy`")
    ap.add_argument("--out-dir", default="outputs/campaign")
    ap.add_argument("--only", type=int, default=None, help="render only this item index")
    ap.add_argument("--dry-run", action="store_true", help="list what would render; render nothing")
    ap.add_argument("--trend", action="store_true", help="pass --trend to each poster (ride a trend)")
    args = ap.parse_args()

    pp, plan_path = Path(args.profile), Path(args.from_plan)
    for p in (pp, plan_path):
        if not p.is_file():
            print(f"!! not found: {p}", file=sys.stderr)
            return 2

    from campaign import plan_creatives, run_all, run_creative

    calendar = json.loads(plan_path.read_text(encoding="utf-8"))
    jobs = plan_creatives(calendar, out_dir=args.out_dir)
    if not jobs:
        print("(no calendar items)", file=sys.stderr)
        return 0

    print(f"[campaign] {len(jobs)} item(s) from {plan_path.name}"
          + (f" — rendering only #{args.only}" if args.only is not None else "")
          + (" — DRY RUN" if args.dry_run else ""))
    for job in jobs:
        if args.only is not None and job.index != args.only:
            continue
        print(f"  #{job.index:2} {job.date} {job.platform:10} {job.creative_type:6} "
              f"\"{job.headline}\" -> {job.out_path}")

    # --trend applies to posters (the reel has no copy-research path).
    runner = run_creative
    if args.trend:
        def runner(job, profile, plan, *, extra_args=()):  # noqa: F811
            extra = ("--trend",) if job.creative_type == "poster" else ()
            return run_creative(job, profile, plan, extra_args=extra + tuple(extra_args))

    results = run_all(jobs, pp, plan_path, runner=runner,
                      dry_run=args.dry_run, only_index=args.only)
    if not args.dry_run:
        ok = sum(1 for _job, rc in results if rc == 0)
        print(f"[campaign] {ok}/{len(results)} creative(s) rendered "
              f"(out: {args.out_dir})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
