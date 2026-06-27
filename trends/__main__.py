"""CLI: show trends relevant to keywords or a business profile.

    python -m trends "ai marketing automation"          # from keywords
    python -m trends --profile profile.json             # keywords from a profile
    python -m trends "jewelry" --require-match --top 5   # only on-topic trends
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass

    ap = argparse.ArgumentParser(prog="trends", description="Trending items for a business.")
    ap.add_argument("keywords", nargs="*", help="topic keywords (space-separated)")
    ap.add_argument("--profile", help="a business_profile.json to derive keywords from")
    ap.add_argument("--top", type=int, default=10, help="how many trends to show")
    ap.add_argument("--per-source", type=int, default=20, help="items fetched per source")
    ap.add_argument("--require-match", action="store_true",
                    help="only show trends that share a keyword with the business")
    args = ap.parse_args()

    from trends import top_trends, keywords_from_profile

    keywords = list(args.keywords)
    if args.profile:
        p = Path(args.profile)
        if not p.is_file():
            print(f"!! profile not found: {p}", file=sys.stderr)
            return 2
        keywords += keywords_from_profile(json.loads(p.read_text(encoding="utf-8")))

    if not keywords:
        print("!! provide keywords or --profile", file=sys.stderr)
        return 2

    print(f"[trends] keywords: {', '.join(keywords[:12])}", file=sys.stderr)
    items = top_trends(keywords, top_k=args.top, limit_per_source=args.per_source,
                       require_match=args.require_match)
    if not items:
        print("(no trends — sources unreachable or no match)", file=sys.stderr)
        return 0
    for i, it in enumerate(items, 1):
        tag = (" [" + ", ".join(it.matched_terms) + "]") if it.matched_terms else ""
        print(f"{i:2}. ({it.trend_score:.2f} {it.source}){tag}  {it.title}")
        print(f"     {it.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
