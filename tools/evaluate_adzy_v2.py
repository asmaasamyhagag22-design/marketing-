"""Replay the frozen research release cases with identical budgets."""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from strategy.campaign_research import MAX_PAGES, MAX_SECONDS, research  # noqa: E402
from workflows.v2_cases import NAME, NOW, ROOT, release_loader  # noqa: E402


def main():
    cases = json.loads((ROOT_DIR / "docs/v2/research-release.json").read_text())
    rows = []
    for case in cases:
        result = {"id": case["id"]}
        for method in ("fixed", "guided"):
            outcome = research(ROOT, NAME, release_loader(case), now=datetime.fromisoformat(NOW), method=method)
            result[method] = {**outcome, "expected": case["expected_" + method]}
        rows.append(result)
    print(json.dumps({"synthetic": True, "max_page_calls_per_case": MAX_PAGES,
                      "max_seconds": MAX_SECONDS, "rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
