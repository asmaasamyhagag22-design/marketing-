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


def _window(text: str, token: str, radius: int = 200) -> str:
    """A ≤2·radius-char window CENTERED on the shared token, so the sentence that justifies (or
    refutes) the match survives truncation. A blind head-slice (text[:400]) can clip away the
    proving context when the token sits deep in a long block — a silent recall edge. Falls back
    to a head-slice when the token isn't found. Only WHICH span the judge sees changes; its
    wording (measurement-locked _SYSTEM) is untouched, and for any text ≤2·radius the result is
    the whole string — identical to the old [:400] on the short claims the judge was tuned on."""
    text = "" if text is None else str(text)      # coerce: this runs BEFORE judge()'s try/except,
    token = "" if token is None else str(token)    # so it must never raise (never-raise guarantee).
    budget = 2 * radius
    if len(text) <= budget:
        return text
    lo = text.lower().find(token.lower()) if token else -1
    if lo < 0:
        return text[:budget]
    start = lo - radius
    end = lo + len(token) + radius
    if start < 0:                                   # clamped left -> slide right to fill the budget
        end -= start
        start = 0
    if end > len(text):                             # clamped right -> slide left to fill the budget
        start = max(0, start - (end - len(text)))
        end = len(text)
    clip = text[start:end]
    return ("…" + clip) if start > 0 else clip


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
            f"CLAIM copy: {_window(claim_text, token)!r}\n"
            f"BRAND evidence: {_window(evidence_text, token)!r}\n"
            "Do the claim and the evidence use this value for the SAME thing?"
        )
        try:
            resp, _usage = caller(_SYSTEM, user, _SameSubject, group_name="ledger_subject_judge")
            val = getattr(resp, "same_subject", None)
            return bool(val) if isinstance(val, bool) else None
        except Exception:  # noqa: BLE001 — a judge error must never fabricate a rejection
            return None

    return judge
