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
