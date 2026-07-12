"""Apify spend guard — enforces the owner's monthly cap ($20/month, on record 2026-07-12).

Apify bills per Actor result; we cannot see dollars at call time, so the guard budgets an
ESTIMATE (results x APIFY_COST_PER_1K_RESULTS, conservative default $5/1k) against a local
JSONL ledger. Pure logic — the only network path stays scripts/pull_facebook.py (PD-4)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEFAULT_LEDGER = Path("runs") / "apify_spend.jsonl"   # runs/ is gitignored


def monthly_cap_usd() -> float:
    return float(os.getenv("APIFY_MONTHLY_CAP_USD", "20"))


def cost_per_1k_usd() -> float:
    return float(os.getenv("APIFY_COST_PER_1K_RESULTS", "5"))


def est_cost_usd(n_results: int, *, cost_per_1k: Optional[float] = None) -> float:
    rate = cost_per_1k if cost_per_1k is not None else cost_per_1k_usd()
    return round(max(0, int(n_results)) * rate / 1000.0, 4)


def month_key(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.now(timezone.utc)
    return f"{d.year:04d}-{d.month:02d}"


def month_spend_usd(ledger: Path = DEFAULT_LEDGER, *, month: Optional[str] = None) -> float:
    """Sum of estimated spend recorded for the month. Missing/corrupt lines count as 0 —
    but a corrupt ledger never silently OPENS budget: callers still add before comparing."""
    mk = month or month_key()
    total = 0.0
    if not ledger.is_file():
        return 0.0
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if row.get("month") == mk:
                total += float(row.get("est_cost_usd") or 0.0)
        except Exception:  # noqa: BLE001
            continue
    return round(total, 4)


def check_budget(planned_results: int, *, ledger: Path = DEFAULT_LEDGER,
                 cap: Optional[float] = None, cost_per_1k: Optional[float] = None,
                 month: Optional[str] = None) -> tuple[bool, str]:
    """(ok, message). ok=False means the pull must NOT run."""
    cap_usd = cap if cap is not None else monthly_cap_usd()
    est = est_cost_usd(planned_results, cost_per_1k=cost_per_1k)
    spent = month_spend_usd(ledger, month=month)
    if spent + est > cap_usd:
        return False, (f"REFUSED: est ${est:.2f} for {planned_results} results + "
                       f"${spent:.2f} already spent this month exceeds the owner's "
                       f"${cap_usd:.2f}/month cap")
    return True, (f"ok: est ${est:.2f} + ${spent:.2f} spent <= ${cap_usd:.2f}/month cap")


def record_pull(actual_results: int, *, url: str, ledger: Path = DEFAULT_LEDGER,
                cost_per_1k: Optional[float] = None, when: Optional[datetime] = None) -> dict:
    d = when or datetime.now(timezone.utc)
    row = {"ts": d.isoformat(), "month": month_key(d), "url": url,
           "results": int(actual_results),
           "est_cost_usd": est_cost_usd(actual_results, cost_per_1k=cost_per_1k)}
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row
