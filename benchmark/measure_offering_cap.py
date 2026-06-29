"""Read-only: is the offerings prompt's 12-item cap a CORPUS-WIDE bottleneck,
or just a te.eg edge case? (rule 2 — measure the pattern before changing.)

Proxy: for each saved manifest, count the FILTERED blocks that sit on
offering-bearing pages (services / products / menu / pricing / booking /
delivery / courses / programs / admissions / catering). A distinct offering
usually spans ~2-4 blocks (title + description + price), so a site with, say,
>36 offering-page blocks (~3x the 12 cap) plausibly has MORE than 12 real
offerings — i.e. the cap would truncate it. This is a directional proxy, NOT an
offering count (it overstates), so read it as "how many sites are rich enough
that 12 is likely binding", not as exact offering totals.

Usage: python -m benchmark.measure_offering_cap
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from scraper.schemas import ScrapeManifest
from business_profile.rules.orchestrator import apply_rules
from business_profile.llm.rag import build_full_evidence_pack

logging.disable(logging.CRITICAL)

REPO = Path(__file__).resolve().parent.parent
SCRAPES = REPO / "scrapes"
_TS_RE = re.compile(r"_\d{8}_\d{6}$")

# Offering-bearing page types (EvidencePack._PAGE_TYPE_SCORE high-value set).
OFFERING_PAGE_TYPES = {
    "services", "products", "menu", "pricing", "booking", "delivery_order",
    "courses", "programs", "admissions", "catering",
}
CAP = 12
RICH = CAP * 3  # ~3 blocks/offering -> >36 offering-page blocks ⇒ likely >12 offerings


def _slug(d: str) -> str:
    return _TS_RE.sub("", d)


def main() -> int:
    manifests = sorted(SCRAPES.glob("*/manifest.json"))
    freshest: dict[str, Path] = {}
    for mp in manifests:
        freshest[_slug(mp.parent.name)] = mp  # later (sorted) wins

    rows = []
    for slug, mp in freshest.items():
        try:
            m = ScrapeManifest.model_validate_json(mp.read_text(encoding="utf-8"))
            prof = apply_rules(m, manifest_path=str(mp))
            full = build_full_evidence_pack(m, prof)
        except Exception as exc:  # noqa: BLE001
            rows.append((slug, -1, f"err:{type(exc).__name__}"))
            continue
        off = sum(1 for b in full.blocks if b.page_type in OFFERING_PAGE_TYPES)
        rows.append((slug, off, ""))

    ok = [r for r in rows if r[1] >= 0]
    ok.sort(key=lambda r: r[1], reverse=True)

    print(f"\nOffering-page block count per site ({len(ok)} sites) — proxy for offering richness\n")
    print(f"{'site':<34}{'offering-page blocks':>22}")
    print("-" * 56)
    for slug, off, _ in ok[:25]:
        flag = "  <- likely >12 offerings (cap binds)" if off >= RICH else ""
        print(f"{slug:<34}{off:>22}{flag}")

    rich = [r for r in ok if r[1] >= RICH]
    some = [r for r in ok if CAP <= r[1] < RICH]
    print("\n--- corpus ---")
    print(f"sites measured:                              {len(ok)}")
    print(f"RICH (>={RICH} offering-page blocks; cap likely binds): {len(rich)}")
    print(f"  -> {', '.join(s for s, _o, _ in rich)}")
    print(f"borderline ({CAP}-{RICH-1} blocks):                       {len(some)}")
    print(f"thin (<{CAP} blocks; cap irrelevant):                  "
          f"{len(ok) - len(rich) - len(some)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
