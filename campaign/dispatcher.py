"""Campaign dispatcher — fan a content calendar OUT into actual creatives.

Closes the loop: `python -m strategy` produces a dated content_plan.json; this maps each
item to a POSTER or a REEL (by content_type), resolves its headline (the item's hook, else
its topic), and runs the existing `python -m poster` / `python -m reel` pipelines with
`--from-plan ... --item N` so every flag (research, trend, brandbook, …) still applies.

`plan_creatives` is PURE (calendar -> jobs) and the runner is INJECTABLE, so the mapping
is fully testable without rendering anything.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

# content_type values that are motion creatives -> reel; everything else -> poster.
_REEL_TYPES = {"reel", "video", "short", "shorts"}


def _creative_type(content_type: str) -> str:
    return "reel" if str(content_type or "").lower() in _REEL_TYPES else "poster"


@dataclass
class CreativeJob:
    index: int
    date: str
    platform: str
    content_type: str
    creative_type: str          # "poster" | "reel"
    headline: str
    out_path: str


def plan_creatives(calendar: dict[str, Any], *, out_dir: str | Path = "outputs/campaign") -> list[CreativeJob]:
    """Map a content-calendar dict (from `strategy`) to one render job per item."""
    out_dir = Path(out_dir)
    jobs: list[CreativeJob] = []
    for i, it in enumerate(calendar.get("items") or []):
        ctype = _creative_type(it.get("content_type"))
        ext = "mp4" if ctype == "reel" else "png"
        headline = (str(it.get("hook") or "").strip() or str(it.get("topic") or "").strip())
        date = str(it.get("date") or "")
        platform = str(it.get("platform") or "")
        stem = f"{date}_{platform}_{i:02d}".replace(" ", "").replace("/", "-")
        jobs.append(CreativeJob(
            index=i, date=date, platform=platform,
            content_type=str(it.get("content_type") or ""),
            creative_type=ctype, headline=headline,
            out_path=str(out_dir / f"{stem}.{ext}"),
        ))
    return jobs


def run_creative(job: CreativeJob, profile_path: str | Path, plan_path: str | Path,
                 *, extra_args: tuple[str, ...] = ()) -> int:
    """Default runner: shell out to the existing poster/reel CLI for ONE job (so every
    flag + the grounded pipeline are reused). Returns the process exit code."""
    Path(job.out_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", job.creative_type, str(profile_path),
           "--from-plan", str(plan_path), "--item", str(job.index),
           "--out", job.out_path, *extra_args]
    return subprocess.run(cmd).returncode


def run_all(
    jobs: list[CreativeJob],
    profile_path: str | Path,
    plan_path: str | Path,
    *,
    runner: Optional[Callable[..., int]] = None,
    dry_run: bool = False,
    only_index: Optional[int] = None,
    extra_args: tuple[str, ...] = (),
) -> list[tuple[CreativeJob, Optional[int]]]:
    """Execute (or, with dry_run, just list) the jobs. `runner(job, profile, plan,
    extra_args=...)` is injectable for tests; defaults to `run_creative`."""
    runner = runner or run_creative
    results: list[tuple[CreativeJob, Optional[int]]] = []
    for job in jobs:
        if only_index is not None and job.index != only_index:
            continue
        if dry_run:
            results.append((job, None))
            continue
        rc = runner(job, profile_path, plan_path, extra_args=extra_args)
        results.append((job, rc))
    return results
