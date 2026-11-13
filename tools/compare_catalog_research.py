"""Replay identical, local publisher HTML through two worktrees without network calls."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from strategy.campaign_planner import PlanInput, build_plan
from strategy.campaign_research import Page


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--cases-only", nargs="+")
    args = parser.parse_args()
    captures = json.loads((args.snapshot / "manifest.json").read_text())
    cases = json.loads(args.cases.read_text())

    def load(url, timeout):
        if url not in captures:
            raise OSError("URL absent from replay")
        path = args.snapshot / captures[url]["file"]
        body = path.read_bytes()
        assert sha256(body).hexdigest() == captures[url]["sha256"]
        return Page(url, body, "public_http_replay")

    report = {}
    for case_name in args.cases_only or cases:
        case = cases[case_name]
        request = PlanInput.model_validate({key: case[key] for key in ("url", "objective", "language")})
        result = build_plan(request, "Buffalo Burger", load,
                            lambda: datetime.fromisoformat(captures[request.url]["captured_at"]).astimezone(timezone.utc))
        report[case_name] = {
            "status": result["status"], "gap": result["planner"]["gap"],
            "trace": result["planner"]["trace"], "evidence_count": len(result["evidence"]),
            "directions": len(result["brief"]["directions"]) if result["brief"] else 0,
            "destination": result["planner"]["options"][0]["destination"] if result["brief"] else None,
            "snapshots": {step["page_url"]: captures.get(step["page_url"], {}).get("sha256")
                          for step in result["planner"]["trace"]},
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
