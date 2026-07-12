"""ABSA — aspect-based sentiment over real customer voice (owner-approved design, R-5).

Grounding is enforced by THIS CODE, never by trusting the model:
  - every mention must carry an `evidence_quote` copied VERBATIM from the cited row —
    a quote that is not a substring of that row's text is REJECTED (substring-rejection);
  - the aspect must exist in the category taxonomy (reviews/taxonomy.py, universal
    default) — alien aspects are rejected;
  - a theme survives only with >= 2 DISTINCT supporting rows (the ratified threshold).

Routing (R-5, deterministic): own-brand praise -> Strengths, own-brand complaint ->
Weaknesses; peer complaint -> Opportunity when the aspect is a controllable service gap
(waiting/booking/communication/...), else Threat; peer praise stays a category note.
Everything enters SWOT through synthesize_swot(themes=) — no second door.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from pydantic import BaseModel

from .taxonomy import aspects_for

_TEXT_CAP = 400          # chars per row sent to the model (token control)
_MIN_SUPPORT = 2         # ratified: a theme needs >= 2 distinct rows

# Peer complaints on these aspects are FIXABLE service gaps -> a differentiation
# opening (Opportunity). Complaints on anything else (quality/price/outcome) read as
# category-level Threat signals. Deterministic — the model never routes.
_SERVICE_GAP_ASPECTS = {
    "waiting_time", "booking", "communication", "staff", "delivery",
    "shipping", "returns", "emergency", "nursing",
}


class AspectMention(BaseModel):
    source_id: str = ""
    aspect: str = ""
    polarity: str = ""            # "praise" | "complaint" (validated in code)
    evidence_quote: str = ""


class _AbsaResponse(BaseModel):
    mentions: List[AspectMention] = []


@dataclass
class AspectTheme:
    aspect: str
    polarity: str                            # "praise" | "complaint"
    text: str                                # human-readable (Arabic label + aspect key)
    support: List[str] = field(default_factory=list)    # distinct row ids
    quotes: List[str] = field(default_factory=list)     # surviving verbatim quotes
    is_own_brand: bool = False


def _norm(s: str) -> str:
    """Whitespace-insensitive comparison key for the substring gate."""
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _row_fields(row: Any, idx: int) -> tuple[str, str, bool]:
    """(id, text, is_own_brand) from a SocialSignal, Review, or plain dict."""
    if isinstance(row, dict):
        text = str(row.get("text") or "")
        own = bool(row.get("is_own_brand", False))
        rid = str(row.get("id") or f"R{idx + 1}")
    else:
        text = str(getattr(row, "text", "") or "")
        own = bool(getattr(row, "is_own_brand", False))
        rid = f"R{idx + 1}"
    return rid, text, own


_SYSTEM = (
    "You are an aspect-based sentiment analyst for real customer reviews and comments, "
    "many in Egyptian Arabic. You NEVER invent: every mention must quote the row VERBATIM."
)

_PROMPT_TEMPLATE = """Below are numbered customer texts. Each line is: [ID] (OWN or PEER) text.
OWN = about the subject brand itself; PEER = about a competitor.

{rows_block}

Allowed aspects (use the exact key):
{aspects_block}

For every clear aspect-level sentiment expressed in a row, return a mention with:
- source_id: the row ID (e.g. R3)
- aspect: one of the allowed aspect keys ONLY
- polarity: "praise" or "complaint"
- evidence_quote: the EXACT words from that row expressing it — copied verbatim,
  character for character. Never paraphrase, never translate, never trim diacritics.
Rules: one mention per (row, aspect); skip rows with no clear aspect sentiment; negation
flips polarity ("مش نضيف" is a complaint). Do not infer aspects that are not in the text.
"""


def extract_aspect_themes(rows: list, *, category: Optional[str] = None,
                          caller: Any = None,
                          min_support: int = _MIN_SUPPORT) -> list[AspectTheme]:
    """Model proposes mentions; CODE keeps only the grounded ones and aggregates themes.
    No caller (or a caller failure) -> [] — SWOT still builds without themes."""
    parsed = [_row_fields(r, i) for i, r in enumerate(rows)]
    parsed = [(rid, t, own) for rid, t, own in parsed if t.strip()]
    if not parsed or caller is None:
        return []
    taxonomy = aspects_for(category)
    allowed = {a["aspect"] for a in taxonomy}
    labels_ar = {a["aspect"]: a["ar"] for a in taxonomy}
    rows_block = "\n".join(
        f"[{rid}] ({'OWN' if own else 'PEER'}) {text[:_TEXT_CAP]}"
        for rid, text, own in parsed)
    aspects_block = "\n".join(f"- {a['aspect']}: {a['ar']} / {a['en']}" for a in taxonomy)
    try:
        resp, _ = caller(_SYSTEM,
                         _PROMPT_TEMPLATE.format(rows_block=rows_block,
                                                 aspects_block=aspects_block),
                         _AbsaResponse, group_name="absa_mentions")
    except Exception:  # noqa: BLE001
        return []

    by_id = {rid: (text, own) for rid, text, own in parsed}
    grouped: dict[tuple[str, str, bool], AspectTheme] = {}
    for m in (resp.mentions if resp else []) or []:
        src = by_id.get((m.source_id or "").strip())
        if src is None:
            continue                                   # cites a row that doesn't exist
        text, own = src
        aspect = (m.aspect or "").strip()
        polarity = (m.polarity or "").strip().lower()
        quote = (m.evidence_quote or "").strip()
        if aspect not in allowed or polarity not in ("praise", "complaint"):
            continue                                   # alien aspect / polarity
        if not quote or _norm(quote) not in _norm(text):
            continue                                   # SUBSTRING-REJECTION: not verbatim
        key = (aspect, polarity, own)
        th = grouped.setdefault(key, AspectTheme(
            aspect=aspect, polarity=polarity,
            text=f"{labels_ar.get(aspect, aspect)} ({aspect})", is_own_brand=own))
        rid = (m.source_id or "").strip()
        if rid not in th.support:
            th.support.append(rid)
            th.quotes.append(quote)
    return [t for t in grouped.values() if len(t.support) >= min_support]


def themes_for_swot(aspect_themes: list[AspectTheme]) -> list:
    """AspectTheme -> competitor.swot.ReviewTheme (the ONLY door into SWOT, per R-5)."""
    from competitor.swot import ReviewTheme
    out = []
    for t in aspect_themes:
        voice = "own" if t.is_own_brand else "peer"
        out.append(ReviewTheme(
            polarity=t.polarity,
            text=t.text,
            # one citation per supporting signal (claim ladder counts these)
            support=[f"{voice} voice {rid}: «{q[:80]}»"
                     for rid, q in zip(t.support, t.quotes)],
            is_unmet_need=(not t.is_own_brand and t.polarity == "complaint"
                           and t.aspect in _SERVICE_GAP_ASPECTS),
            is_own_brand=t.is_own_brand,
        ))
    return out
