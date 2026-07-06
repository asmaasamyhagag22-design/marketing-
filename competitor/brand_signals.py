"""Brand-level SWOT signals from the grounded business profile.

The mechanical gap matrix (matrix.py) sees a brand as page attributes — cta_count, whatsapp,
social_count. A strategist's SWOT leads with the BRAND: its distinctive promises and its proof.
Those signals already live in the profile (`value_propositions`, `trust_signals` — each a grounded
EvidencedField) but `synthesize_swot` threw them away. This module mines them into Strengths, every
line GATED by the same Evidence Ledger the rest of the pipeline uses (no free-form invention: a line
whose hard claims don't resolve to real evidence is DROPPED). Universal — keyed only off generic
profile fields that exist for every brand, never a vertical or brand name.
"""
from __future__ import annotations

from typing import Any

from competitor.swot import SWOTItem


# Trust signals are proof points, but a site also lists generic ones ("Secure Payments",
# "International Shipping"). Keep only signals carrying REAL proof — a number/social-proof figure
# or a substantive claim keyword — so Strengths stay differentiators, not checkout boilerplate.
_TRUST_PROOF_KEYS = (
    "certif", "award", "iso", "haccp", "guarantee", "warrant", "cruelty", "vegan", "organic",
    "handmade", "handcraft", "hand-craft", "official", "authorized", "authorised", "since",
    "year", "trusted", "loved", "rated", "star", "customer", "client", "patient", "member",
    "no animal", "natural ingredient",
)


# Strategist phrasing for the subject's own-site dimensions, so a standalone SWOT reads like a
# strategist wrote it ("Thin conversion path (3 CTAs)") instead of a raw attribute dump
# ("Number of CTAs: 3"). TEXT ONLY — the SWOTItem's citation/evidence/claim_strength are unchanged,
# and the cell is the same scrape-grounded fact. Keyed off dim.key (universal; no vertical wording).
_DIM_STRONG = {   # present / count > 0
    "online_booking": "Online booking available on-site",
    "whatsapp": "Direct WhatsApp contact channel",
    "shows_reviews": "Customer reviews shown on-site",
    "bilingual": "Bilingual site (Arabic + English)",
    "cta_count": "Clear conversion paths ({v} calls-to-action)",
    "offerings_count": "Broad offering range ({v} lines)",
    "trust_count": "Visible trust markers ({v} on-site)",
    "social_count": "Active social presence ({v} channels)",
}
_DIM_WEAK = {     # absent / count == 0
    "online_booking": "No online booking path on-site",
    "whatsapp": "No WhatsApp contact channel",
    "shows_reviews": "No customer reviews shown on-site",
    "bilingual": "Single-language site (missing Arabic/English)",
    "cta_count": "No clear call-to-action on the page",
    "offerings_count": "No offerings surfaced on-site",
    "trust_count": "No visible trust markers on-site",
    "social_count": "No social links on-site",
}


def phrase_dimension(dim_key: str, label: str, kind: str, value: Any, positive: bool) -> str:
    """Strategist phrasing for one own-site dimension. Falls back to a clean label-based phrase for
    any dimension not in the tables (so a new dimension never regresses to a raw dump)."""
    tmpl = (_DIM_STRONG if positive else _DIM_WEAK).get(dim_key)
    if tmpl:
        return tmpl.format(v=value) if "{v}" in tmpl else tmpl
    if kind == "count":
        return f"{label}: {value}" if positive else f"{label}: none on-site"
    return f"{label} present on-site" if positive else f"{label} not on-site"


def _val(x: Any) -> str:
    if isinstance(x, dict):
        return str(x.get("value") or "").strip()
    return str(x or "").strip()


def _unwrap(profile: Any) -> dict:
    """Accept a BusinessProfile dict or a {'profile': {...}} full-run wrapper."""
    if isinstance(profile, dict) and "value_propositions" not in profile \
            and isinstance(profile.get("profile"), dict):
        return profile["profile"]
    return profile if isinstance(profile, dict) else {}


def _is_strong_trust(text: str) -> bool:
    low = text.lower()
    return any(ch.isdigit() for ch in text) or any(k in low for k in _TRUST_PROOF_KEYS)


def _gated(ledger: Any, text: str) -> bool:
    """The EXACT gate tows.py / strategy use: EVERY hard claim in the line must resolve to real
    evidence. Fails CLOSED (drop) on any ledger error. No ledger -> gating off (pass)."""
    if ledger is None:
        return True
    try:
        return all(v.sourced for v in ledger.audit_text(text or ""))
    except Exception:
        return False


def strengths_from_profile(profile: Any, ledger: Any = None) -> list[SWOTItem]:
    """Brand-level Strengths from the grounded profile: distinctive value propositions and real
    proof points. Each cites its profile field; claim_strength='internally_supported' (own-site
    truth, not peer-validated). Ledger-gated + de-duplicated. [] on an empty/absent profile."""
    p = _unwrap(profile)
    out: list[SWOTItem] = []
    seen: set[str] = set()

    def emit(text: str, field: str) -> None:
        t = (text or "").strip()
        k = t.lower()
        if not t or k in seen or not _gated(ledger, t):
            return
        seen.add(k)
        out.append(SWOTItem(text=t, citation=["your profile", field],
                            evidence=f"brand signal ({field})",
                            claim_strength="internally_supported"))

    for vp in (p.get("value_propositions") or []):
        emit(_val(vp), "value_propositions")
    for ts in (p.get("trust_signals") or []):
        t = _val(ts)
        if _is_strong_trust(t):
            emit(t, "trust_signals")
    return out
