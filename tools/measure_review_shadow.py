"""Replay frozen public and synthetic capture pairs without calling a model or editing approvals."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from strategy.positioning.refresh_shadow import compare_captures  # noqa: E402

FIXTURES = ROOT / "docs/experiments/review-shadow"
INPUT_DIGESTS = {
    "cases.json": "6dbe2968e14f9cbd7073e50c917119f364cafd09e4007e7d69c7d4b5a37f6962",
    "labels.json": "d31757d2f7b5296282b7602e1f7da195cf72c4dacb865454f25827eb70a8d316",
}


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def load_frozen(name):
    raw = (FIXTURES / name).read_bytes()
    if digest(raw) != INPUT_DIGESTS[name]:
        raise ValueError(f"Frozen input changed: {name}")
    return json.loads(raw)


def capture(snapshot):
    return {"representation": snapshot["representation"], "complete": snapshot["complete"],
            "pages": {url: row["sha256"] if "sha256" in row else digest(row["body"].encode())
                      for url, row in snapshot["pages"].items()}}


def verify_public(cases):
    bodies = {}
    for case in cases:
        if case["kind"] != "public":
            continue
        for side in ("before", "after"):
            for page, row in case[side]["pages"].items():
                url = row["raw_url"]
                if url not in bodies:
                    with urlopen(url, timeout=20) as response:
                        bodies[url] = response.read()
                body = bodies[url]
                if digest(body) != row["sha256"]:
                    raise ValueError(f"Public revision changed: {url}")
                if side == "before":
                    for dependency in case["dependencies"]:
                        if dependency["page_url"] == page and dependency["before_quote"].encode() not in body:
                            raise ValueError(f"Quote missing from frozen public revision: {url}")
    return len(bodies)


def summarize(results):
    labels = Counter(row["expected"] for row in results)
    matrix = {label: dict(Counter(row["decision"] for row in results if row["expected"] == label))
              for label in ("REQUIRED", "REDUNDANT", "UNKNOWN")}
    return {
        "pairs": len(results),
        "baseline": {"reviews": len(results), "redundant_reviews": labels["REDUNDANT"],
                     "material_misses": 0},
        "avoided_redundant_reviews": [matrix["REDUNDANT"].get("SKIP", 0), labels["REDUNDANT"]],
        "missed_material_changes": [matrix["REQUIRED"].get("SKIP", 0), labels["REQUIRED"]],
        "shadow_unknown": [sum(row["decision"] == "UNKNOWN" for row in results), len(results)],
        "unlabelable": [labels["UNKNOWN"], len(results)],
        "skipped_without_known_label": matrix["UNKNOWN"].get("SKIP", 0),
        "shadow_review_or_defer": sum(row["decision"] != "SKIP" for row in results),
        "label_by_shadow_decision": matrix,
    }


def evaluate(*, check_public=False):
    cases = load_frozen("cases.json")
    fetched = verify_public(cases) if check_public else None
    results = []
    elapsed_ms = []
    for case in cases:
        before, after = capture(case["before"]), capture(case["after"])
        start = perf_counter()
        shadow = compare_captures(before, after, case["dependencies"])
        elapsed_ms.append(1000 * (perf_counter() - start))
        results.append({"id": case["id"], "kind": case["kind"], **shadow})

    labels = load_frozen("labels.json")
    if len(results) != len(labels) or {row["id"] for row in results} != labels.keys():
        raise ValueError("Frozen labels and cases differ")
    for row in results:
        row.update(labels[row["id"]])
    report = {key: summarize([row for row in results if key == "all" or row["kind"] == key])
              for key in ("all", "public", "synthetic")}
    return {"input_sha256": INPUT_DIGESTS, "verified_public_revisions": fetched,
            "provider_requests": 0, "comparison_total_ms": round(sum(elapsed_ms), 3),
            "summary": report, "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-public", action="store_true",
                        help="Fetch immutable publisher files and verify digests and original quotes.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(check_public=args.verify_public)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
