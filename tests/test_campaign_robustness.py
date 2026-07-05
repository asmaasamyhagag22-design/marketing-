"""Campaign dispatcher robustness (2026-07-05 audit).

- `plan_creatives` tolerates a hand-edited/malformed plan (non-dict calendar, missing
  `items`, non-dict item) instead of raising a raw traceback,
- `run_all` does NOT abort the whole fan-out when one job's runner fails to launch — it
  records that item as failed (rc=1) and continues,
- a failed render is visible to callers (the CLI now returns non-zero; here we assert the
  per-job result codes the CLI derives its exit code from).

Hermetic: injected runner, no subprocess / no rendering.
"""
from campaign import plan_creatives, run_all, CreativeJob


def _job(i):
    return CreativeJob(index=i, date="2026-07-05", platform="instagram",
                       content_type="post", creative_type="poster",
                       headline=f"h{i}", out_path=f"out/{i}.png")


# --- plan_creatives tolerance ------------------------------------------------------------
def test_plan_creatives_on_valid_calendar():
    cal = {"items": [{"content_type": "reel", "hook": "Hi", "date": "2026-07-05",
                      "platform": "tiktok"}]}
    jobs = plan_creatives(cal)
    assert len(jobs) == 1 and jobs[0].creative_type == "reel"


def test_plan_creatives_tolerates_malformed_calendar():
    assert plan_creatives([]) == []                    # not a dict
    assert plan_creatives({}) == []                    # no 'items'
    assert plan_creatives({"items": None}) == []
    assert plan_creatives("garbage") == []             # not a dict at all


def test_plan_creatives_skips_non_dict_items():
    cal = {"items": [{"content_type": "post", "topic": "A"}, "not-a-dict", None,
                     {"content_type": "reel", "topic": "B"}]}
    jobs = plan_creatives(cal)
    assert len(jobs) == 2                               # the two real items only


# --- run_all resilience ------------------------------------------------------------------
def test_run_all_continues_when_one_job_raises():
    jobs = [_job(0), _job(1), _job(2)]

    def flaky_runner(job, profile, plan, *, extra_args=()):
        if job.index == 1:
            raise FileNotFoundError("python not found")
        return 0

    results = run_all(jobs, "p.json", "plan.json", runner=flaky_runner)
    assert len(results) == 3                            # NONE dropped — fan-out completed
    codes = {j.index: rc for j, rc in results}
    assert codes[0] == 0 and codes[2] == 0
    assert codes[1] == 1                                # the raising job -> recorded failed


def test_run_all_records_nonzero_returncodes():
    jobs = [_job(0), _job(1)]

    def runner(job, profile, plan, *, extra_args=()):
        return 0 if job.index == 0 else 3              # #1 "fails" with rc 3

    results = run_all(jobs, "p.json", "plan.json", runner=runner)
    ok = sum(1 for _j, rc in results if rc == 0)
    assert ok == 1                                     # the CLI would exit non-zero (ok < total)


def test_run_all_dry_run_renders_nothing():
    jobs = [_job(0), _job(1)]
    calls = {"n": 0}

    def runner(job, profile, plan, *, extra_args=()):
        calls["n"] += 1
        return 0

    results = run_all(jobs, "p.json", "plan.json", runner=runner, dry_run=True)
    assert calls["n"] == 0 and all(rc is None for _j, rc in results)
