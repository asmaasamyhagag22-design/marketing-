"""Recalculate archived writing scores and offline acceptance from committed evidence."""
from argparse import ArgumentParser
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

from pydantic import ValidationError

from strategy.campaign_planner import BriefReview, review_draft
from strategy.campaign_v2 import CampaignConflict


ROOT = Path(__file__).resolve().parents[1] / "docs" / "campaigns" / "quality"
FIELDS = ("headline", "message", "cta", "caption")
DEVELOPMENT = ("firefox", "firefox-download", "lego", "rijksmuseum")
HELDOUT = ("diffchecker", "brave")


def load(path):
    return json.loads(path.read_text())


def scores(rows):
    return {
        "directions": len(rows), "headline_pass": sum(row[0] for row in rows),
        "cta_pass": sum(row[1] for row in rows),
        "claim_fields_beyond_evidence": sum(len(row[2]) for row in rows),
        "directions_beyond_evidence": sum(bool(row[2]) for row in rows),
    }


def acceptance(previous, copy):
    brief = previous["brief"]
    try:
        review_draft(previous, BriefReview(audience=brief["audience"], tone=brief["tone"],
                                          selected=brief["selected"], copy_edit=copy))
    except ValidationError:
        return "COPY_SCHEMA"
    except CampaignConflict as error:
        return str(error)
    return "ACCEPTED"


def summarize():
    editorial = load(ROOT / "results/editorial.json")
    ledger, results = ROOT / "ledger", ROOT / "results"
    for case in DEVELOPMENT:
        compact = load(ledger / f"compact-{case}-vertex.dispatch.json")["input"]
        direct = load(ledger / f"direct-{case}-vertex.dispatch.json")["input"]
        assert all(compact[key] == direct[key] for key in ("evidence", "destination", "action", "baseline")), case

    artifacts = {}
    for file in sorted(results.glob("*/*.zip")):
        if file.name.startswith("recovered"):
            continue
        report = load(file.with_suffix(".json"))
        with ZipFile(file) as archive:
            assert report == json.loads(archive.read("campaign.json"))
            for size, measure in report["poster_measurements"].items():
                assert sha256(archive.read(f"poster-{size}.png")).hexdigest() == measure["sha256"]
        artifacts[str(file.relative_to(results))] = sha256(file.read_bytes()).hexdigest()
    restored = results / "rijksmuseum/recovered.zip"
    artifacts[str(restored.relative_to(results))] = sha256(restored.read_bytes()).hexdigest()

    summary = {"scores": {}, "model_candidate_gate": {}, "artifacts": artifacts}
    for method in ("previous_rules", "release_rules_or_accepted_edit", "compact_with_brief", "direct_without_brief"):
        for label, cases in (("development", DEVELOPMENT), ("heldout", HELDOUT)):
            cases = [case for case in cases if case in editorial[method]]
            if not cases:
                continue
            rules = method in {"previous_rules", "release_rules_or_accepted_edit"}
            rows = [row for case in cases
                    for row in ([editorial[method][case]] if rules else editorial[method][case])]
            summary["scores"][f"{method}/{label}"] = scores(rows)
            if rules:
                continue
            round_name = "direct" if method == "direct_without_brief" else "heldout" if label == "heldout" else "compact"
            for case in cases:
                draft = load(results / case / "draft.json")["proposal"]
                raw = load(ledger / f"{round_name}-{case}-vertex.receipt.json")
                assert raw["outcome"] == "COMPLETE"
                directions = json.loads(raw["content"])["directions"]
                rating = editorial[method][case]
                assert len(directions) == len(rating) == 3
                verdicts = []
                for choice, row in zip(directions, rating):
                    copy = {field: choice[field] for field in FIELDS}
                    verdicts.append({"editorially_eligible": bool(row[0] and row[1] and not row[2]),
                                     "verdict": acceptance(draft, copy)})
                summary["model_candidate_gate"][f"{round_name}/{case}"] = verdicts

    receipts = [load(path) for path in ledger.glob("*.receipt.json")]
    estimated = sum((Decimal(row["estimated_charge"]) for row in receipts if row["estimated_charge"]), Decimal(0))
    holds = len(receipts) - sum(row["estimated_charge"] is not None for row in receipts)
    summary["cost"] = {"attempts": len(receipts), "estimated_usd": str(estimated), "holds": holds,
                       "remaining_after_holds_usd": str(Decimal(10) - estimated - holds * Decimal("0.01"))}
    return summary


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = json.dumps(summarize(), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")
