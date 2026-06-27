"""Campaign dispatcher: fan a content calendar out into posters + reels.

    from campaign import plan_creatives, run_all
    jobs = plan_creatives(calendar)
    run_all(jobs, "profile.json", "content_plan.json")
"""
from .dispatcher import CreativeJob, plan_creatives, run_creative, run_all

__all__ = ["CreativeJob", "plan_creatives", "run_creative", "run_all"]
