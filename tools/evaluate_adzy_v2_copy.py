"""Compare literal transfer and structured Arabic copy on the frozen release cases."""
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
from strategy.campaign_research import Page, ResearchGap, parse_offer  # noqa: E402
from strategy.campaign_v2 import propose  # noqa: E402
from workflows.v2_cases import NAME, NOW, ROOT, offer_page  # noqa: E402


def main():
    rows = []
    cases = json.loads((ROOT_DIR / "docs/v2/copy-release.json").read_text())
    for case in cases:
        fixture = {key: value for key, value in case.items() if key not in {"id", "eligible"}}
        page = Page(ROOT + "offer", offer_page(**fixture))
        row = {"id": case["id"], "expected_eligible": case["eligible"]}
        try:
            offer = parse_offer(page, NAME, datetime.fromisoformat(NOW))
        except ResearchGap as exc:
            rows.append({**row, "status": "REFUSED", "reason": str(exc)})
            continue
        result = propose("زيادة حجوزات التجربة", NAME, {"offer": offer.as_dict()})
        fields = offer.fields
        copy = result["creative"]["copy"]
        expiry = datetime.fromisoformat(fields["availabilityEnds"])
        offset = expiry.strftime("%z")
        checks = {
            "price_and_currency": copy["price"] == f"{case['price']} {case['currency']}",
            "branch": copy["branch"] == case["branch"],
            "terms": copy["terms"] == case["terms"],
            "validity": copy["validity"] == f"{expiry:%Y-%m-%d %H:%M:%S} (UTC{offset[:3]}:{offset[3:]})",
        }
        rows.append({**row, "status": "DRAFT", "checks": checks,
                     "literal_baseline": {"body": " | ".join(fields.values()), "cta": None},
                     "arabic": copy,
                     "strategy_fields_present": all(result["strategy"][key] for key in
                         ("recommendation", "assumption", "alternative", "tradeoff", "metric"))})
    print(json.dumps({"synthetic": True, "rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
