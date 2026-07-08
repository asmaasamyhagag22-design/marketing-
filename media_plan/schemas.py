"""U1 Media Plan — core schemas (first draft: MetaObjective + CampaignObjective).

The Media Plan answers the question the campaign defense actually asks: *what ONE objective should
this brand run, and why?* Everything here is grounded — a CampaignObjective is only trustworthy if
its rationale resolves to the brand's real evidence (the same discipline as the profile extractor:
`value` + provenance, never an assertion).

Design rules (frozen, INTERFACES.md §F + the Prime Directives):
- PD-5: NEW models are STRICT — `extra="forbid"` so a typo'd field fails loudly, never silently drops.
- PD-2: `business_profile` is untouched; we REUSE its `EvidenceItem` / `Confidence` rather than fork them.
- PD-4: no network in this module — it defines types the builder fills via the Caller / MockCaller.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# Reuse the profile's evidence primitives — one provenance vocabulary across the whole system.
from business_profile.schemas import Confidence, EvidenceItem


class MetaObjective(str, Enum):
    """The SIX Meta (Facebook / Instagram) campaign objectives under the current ODAX consolidation.

    The `.value` is the exact Meta Ads API objective string, so a CampaignObjective serializes
    straight into an Ads-Manager import (U6 launch bundle) with no translation layer. Every Meta
    campaign is exactly one of these — there is no seventh.
    """
    AWARENESS = "OUTCOME_AWARENESS"          # be seen/remembered by the right people (reach, brand lift)
    TRAFFIC = "OUTCOME_TRAFFIC"              # send people to a destination (site, WhatsApp, profile)
    ENGAGEMENT = "OUTCOME_ENGAGEMENT"        # messages, video views, post/page engagement
    LEADS = "OUTCOME_LEADS"                  # collect leads (instant forms, calls, sign-ups)
    APP_PROMOTION = "OUTCOME_APP_PROMOTION"  # app installs + in-app actions
    SALES = "OUTCOME_SALES"                  # purchases / conversions (needs a store or a pixel/CAPI)

    @property
    def label(self) -> str:
        """Human-facing name (for the plan UI / defense), not the API string."""
        return {
            "OUTCOME_AWARENESS": "Awareness",
            "OUTCOME_TRAFFIC": "Traffic",
            "OUTCOME_ENGAGEMENT": "Engagement",
            "OUTCOME_LEADS": "Leads",
            "OUTCOME_APP_PROMOTION": "App promotion",
            "OUTCOME_SALES": "Sales",
        }[self.value]


class Destination(str, Enum):
    """WHERE the objective drives the customer — the concrete conversion surface. The deduced
    objective is only actionable paired with a destination the brand ACTUALLY has (a Sales
    objective needs a store; a Leads objective needs a form/WhatsApp/phone)."""
    WEBSITE = "website"
    ONLINE_STORE = "online_store"        # a real cart/checkout (a precondition for a credible SALES objective)
    WHATSAPP = "whatsapp"
    MESSENGER = "messenger"
    INSTAGRAM_DM = "instagram_dm"
    LEAD_FORM = "lead_form"              # Meta instant form
    PHONE_CALL = "phone_call"
    APP = "app"
    PHYSICAL_STORE = "physical_store"    # foot traffic / store visits
    PROFILE = "profile"                  # grow the page/profile itself


class KPITarget(BaseModel):
    """The primary metric this objective is judged on. Values are OPTIONAL — an honest plan states
    the metric it will optimise even before a numeric target is set (targets need historical data
    or a benchmark, which may be UNKNOWN at plan time)."""
    model_config = ConfigDict(extra="forbid")

    metric: str                                    # e.g. "cost_per_lead", "roas", "reach", "cpc"
    target_value: Optional[float] = None           # None = optimise the metric, target TBD (honest-unknown)
    unit: str = ""                                 # "EGP", "%", "count", "ratio"
    window_days: Optional[int] = None              # measurement window; None = campaign lifetime


class EvidenceRef(BaseModel):
    """A resolution-wrapper: a deduction CLAIM plus the real evidence that supports it. `resolved`
    is set True only once the claim's evidence is checked against the Evidence Ledger (the builder
    does this) — an UNresolved ref is a hypothesis, not a fact, and must not drive a decision."""
    model_config = ConfigDict(extra="forbid")

    claim: str                                     # e.g. "the brand sells products through an online store"
    evidence: List[EvidenceItem] = Field(default_factory=list)
    resolved: bool = False                         # True once Ledger-verified

    @property
    def is_grounded(self) -> bool:
        return self.resolved and bool(self.evidence)


class CampaignObjective(BaseModel):
    """The deduced ONE objective for a brand, with its destination, KPI, and grounded rationale.

    This is the load-bearing output of U1: the defense reads `objective` + `rationale` and must be
    able to trace WHY. So `rationale` is never free-floating — it is backed by `evidence` refs that
    resolve to the brand's real facts. `alternatives` records the runners-up so the choice is
    auditable (why LEADS over SALES), not a black box.
    """
    model_config = ConfigDict(extra="forbid")

    objective: MetaObjective
    destination: Destination
    rationale: str                                 # one clear sentence: why THIS objective for THIS brand
    evidence: List[EvidenceRef] = Field(default_factory=list)
    kpi_target: Optional[KPITarget] = None
    confidence: Confidence = Confidence.NONE
    alternatives: List[MetaObjective] = Field(default_factory=list)   # considered-but-not-chosen, in order

    @property
    def is_grounded(self) -> bool:
        """True when the objective's rationale is backed by at least one Ledger-resolved evidence
        ref — the gate a CampaignObjective must pass before it can enter a MediaPlan."""
        return any(ref.is_grounded for ref in self.evidence)
