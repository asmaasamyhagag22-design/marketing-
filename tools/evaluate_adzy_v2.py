"""Replay the frozen research cases or probe a public publisher without a provider."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from strategy.campaign_research import MAX_PAGES, MAX_SECONDS, load_public_page, research  # noqa: E402
from workflows.v2_cases import NAME, NOW, ROOT, release_loader  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-url")
    parser.add_argument("--offer-name")
    args = parser.parse_args()
    if bool(args.public_url) != bool(args.offer_name):
        parser.error("--public-url and --offer-name must be used together")
    if args.public_url:
        now = datetime.now(timezone.utc)
        outcome = research(args.public_url, args.offer_name, load_public_page)
        print(json.dumps({"synthetic": False, "started_at": now.isoformat(), "offer_name": args.offer_name,
                          "result": outcome}, ensure_ascii=False, indent=2))
        return
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
