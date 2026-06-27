"""Evidence Ledger — the central grounding gate.

The product's moat is *provable* grounding: every hard claim in any customer-facing
creative (poster, reel, calendar copy) must trace to a real source the agency can show
its client. This package is that single gate.

Public API:
    EvidenceLedger.from_profile(profile_dict)  -> build the ledger for one brand
    ledger.resolve_claim(text)                 -> Resolution | None
    ledger.audit_text(text)                    -> list[ClaimVerdict]
    ledger.audit_fields({field: text, ...})    -> AuditReport (with .export() trail)

See grounding/ledger.py for the full contract. Step 1 (current) wires this in
OBSERVE-ONLY mode to MEASURE how often the live copy paths emit an unsourced claim;
the blocking gate + regenerate loop is a later, separate step.
"""
from __future__ import annotations

from .ledger import (
    AuditReport,
    Claim,
    ClaimVerdict,
    EvidenceLedger,
    FieldAudit,
    LedgerEntry,
    Resolution,
    extract_claims,
)

__all__ = [
    "EvidenceLedger",
    "Resolution",
    "Claim",
    "ClaimVerdict",
    "FieldAudit",
    "AuditReport",
    "LedgerEntry",
    "extract_claims",
]
