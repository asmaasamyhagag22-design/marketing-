"""Campaign dispatcher — calendar -> creative jobs (pure mapping + injectable runner)."""
from __future__ import annotations

from pathlib import Path

from campaign import plan_creatives, run_all


def _calendar():
    return {
        "business_name": "Brand", "start_date": "2026-06-20", "days": 7,
        "items": [
            {"date": "2026-06-20", "platform": "instagram", "content_type": "reel",
             "topic": "Topic1", "hook": "Hook One"},
            {"date": "2026-06-21", "platform": "tiktok", "content_type": "post",
             "topic": "Topic2", "hook": ""},
            {"date": "2026-06-22", "platform": "linkedin", "content_type": "carousel",
             "topic": "Topic3"},
        ],
    }


def test_plan_maps_creative_type_headline_and_extension(tmp_path: Path):
    jobs = plan_creatives(_calendar(), out_dir=tmp_path)
    assert [j.creative_type for j in jobs] == ["reel", "poster", "poster"]
    assert jobs[0].out_path.endswith(".mp4")          # reel -> mp4
    assert jobs[1].out_path.endswith(".png")          # poster -> png
    assert jobs[0].headline == "Hook One"             # hook wins
    assert jobs[1].headline == "Topic2"               # empty hook -> topic
    assert jobs[2].headline == "Topic3"               # missing hook -> topic


def test_run_all_dry_run_calls_nothing():
    jobs = plan_creatives(_calendar())
    calls = []
    res = run_all(jobs, "p.json", "plan.json",
                  runner=lambda *a, **k: calls.append(a) or 0, dry_run=True)
    assert calls == []
    assert len(res) == 3 and all(rc is None for _job, rc in res)


def test_run_all_invokes_runner_per_job_and_only_index():
    jobs = plan_creatives(_calendar())
    seen = []

    def fake(job, profile, plan, *, extra_args=()):
        seen.append((job.index, job.creative_type))
        return 0

    res = run_all(jobs, "p.json", "plan.json", runner=fake)
    assert [s[0] for s in seen] == [0, 1, 2]
    assert all(rc == 0 for _job, rc in res)

    seen.clear()
    run_all(jobs, "p.json", "plan.json", runner=fake, only_index=1)
    assert seen == [(1, "poster")]                    # only item 1


def test_reel_brief_honors_headline_override():
    from reel import build_reel_brief
    profile = {"name": {"value": "Glamira"}, "category": {"value": "jewelry"}}
    b = build_reel_brief(profile, headline_override="Lab-Grown Sparkle")
    assert b.headline == "Lab-Grown Sparkle"
    b2 = build_reel_brief(profile)                     # no override -> verbatim selection/name
    assert b2.headline and b2.headline != "Lab-Grown Sparkle"
