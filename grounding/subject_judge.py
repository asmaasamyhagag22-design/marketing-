"""Semantic same-subject judge for the Evidence Ledger's C2 residual gate.

The ledger's DETERMINISTIC gate already tells a %/price/duration/scale claim from a bare one
and whether a number/superlative's SUBJECT token overlaps the evidence's. What a token check
CANNOT do is decide, on a token-DISJOINT subject, whether it is an acceptable synonym /
inflection ("5000 experts" vs "5000 youth", "رقمي" vs "رقميون") or a genuine fabrication
("100 free gifts" vs "100 stores", "best coffee" vs "best regards"). Both are token-disjoint;
the difference is semantic. This wraps a cheap LLM caller into that one judgment.

The ledger consults it ONLY on the ambiguous case and caches by (claim, evidence, token), so
cost is bounded to a few cheap calls per asset. Any error -> None -> the gate stays lenient
(it never blocks a plausibly-real claim), so the moat only ever gets STRICTER with a judge,
never regresses without one.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

_SYSTEM = (
    "You check a marketing CLAIM against a brand's REAL evidence. The shared value (a number, "
    "or a ranking/superlative word) already appears in BOTH — decide ONLY whether it describes "
    "the SAME THING.\n"
    "- same_subject=true (accept): synonyms / inflections of ONE subject — '5000 experts' vs "
    "'train 5000 youth'; 'روّاد التحول الرقمي' vs 'الرواد الرقميون'; 'best coffee' vs 'finest brew'.\n"
    "- same_subject=false (reject): the value is about an UNRELATED thing — '100 free gifts' vs "
    "'100 stores'; 'the best coffee' vs 'best regards'; '50% off' vs '50 years'.\n"
    "When genuinely unsure, answer true — never block a plausibly-real claim."
)


def make_subject_judge(caller: Any) -> Optional[Callable[[str, str, str], Optional[bool]]]:
    """Build a same-subject judge from a Gemini caller (use a cheap Flash caller — the judge
    fires only on ambiguous claims). Returns a callable ``(claim_text, evidence_text, token)
    -> True | False | None``, or ``None`` when no caller is given (the ledger then stays
    deterministic + lenient). Never raises."""
    if caller is None:
        return None
    try:
        from pydantic import BaseModel
    except Exception:  # pragma: no cover - pydantic is always present in this project
        return None

    class _SameSubject(BaseModel):
        same_subject: bool

    def judge(claim_text: str, evidence_text: str, token: str) -> Optional[bool]:
        user = (
            f"Shared value/word: {token!r}\n"
            f"CLAIM copy: {(claim_text or '')[:400]!r}\n"
            f"BRAND evidence: {(evidence_text or '')[:400]!r}\n"
            "Do the claim and the evidence use this value for the SAME thing?"
        )
        try:
            resp, _usage = caller(_SYSTEM, user, _SameSubject, group_name="ledger_subject_judge")
            val = getattr(resp, "same_subject", None)
            return bool(val) if isinstance(val, bool) else None
        except Exception:  # noqa: BLE001 — a judge error must never fabricate a rejection
            return None

    return judge
