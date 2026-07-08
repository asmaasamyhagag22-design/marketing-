"""U1 Media Plan — core schema contracts. Hermetic (no network, no LLM).

Pins the frozen facts a downstream unit (builder, launch bundle, defense) relies on: there are
EXACTLY six Meta objectives with the real ODAX API strings; a CampaignObjective is strict and only
counts as grounded when its rationale resolves to real evidence.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from business_profile.schemas import Confidence, EvidenceItem
from media_plan.schemas import (
    CampaignObjective, Destination, EvidenceRef, KPITarget, MetaObjective,
)


def test_there_are_exactly_six_meta_objectives_with_odax_api_values():
    assert len(MetaObjective) == 6
    assert {o.value for o in MetaObjective} == {
        "OUTCOME_AWARENESS", "OUTCOME_TRAFFIC", "OUTCOME_ENGAGEMENT",
        "OUTCOME_LEADS", "OUTCOME_APP_PROMOTION", "OUTCOME_SALES",
    }
    # the .value IS the Ads-API string (so it imports into Ads Manager with no translation)
    assert MetaObjective.SALES.value == "OUTCOME_SALES"
    assert MetaObjective.LEADS.label == "Leads"


def _ev() -> EvidenceItem:
    return EvidenceItem(page_url="https://brand.example/shop", quote="Add to cart", extractor="rule:cart_link")


def test_campaign_objective_is_strict_and_rejects_unknown_fields():
    obj = CampaignObjective(objective=MetaObjective.SALES, destination=Destination.ONLINE_STORE,
                            rationale="The brand runs a real online store with checkout.")
    assert obj.objective is MetaObjective.SALES
    with pytest.raises(ValidationError):
        CampaignObjective(objective=MetaObjective.SALES, destination=Destination.ONLINE_STORE,
                          rationale="x", objectiv=MetaObjective.LEADS)   # typo'd field -> loud fail


def test_objective_is_grounded_only_when_evidence_resolves_against_the_ledger():
    # an unresolved ref is a hypothesis, not a fact -> NOT grounded
    hypo = EvidenceRef(claim="sells online", evidence=[_ev()], resolved=False)
    obj = CampaignObjective(objective=MetaObjective.SALES, destination=Destination.ONLINE_STORE,
                            rationale="sells online", evidence=[hypo])
    assert obj.is_grounded is False

    # once the builder resolves it against the Ledger -> grounded
    obj.evidence[0].resolved = True
    assert obj.evidence[0].is_grounded is True and obj.is_grounded is True

    # resolved but WITHOUT evidence is still not grounded (no fact to trace to)
    empty = EvidenceRef(claim="assumed", evidence=[], resolved=True)
    assert empty.is_grounded is False


def test_kpi_target_allows_honest_unknown_target():
    # the metric is known even when the numeric target is not (needs benchmark data, may be UNKNOWN)
    kpi = KPITarget(metric="cost_per_lead", unit="EGP")
    assert kpi.target_value is None and kpi.metric == "cost_per_lead"
    full = KPITarget(metric="roas", target_value=3.0, unit="ratio", window_days=14)
    assert full.target_value == 3.0 and full.window_days == 14


def test_campaign_objective_round_trips_through_json_with_api_objective_string():
    obj = CampaignObjective(
        objective=MetaObjective.LEADS, destination=Destination.WHATSAPP,
        rationale="No online checkout; the brand takes bookings via WhatsApp, so collect leads.",
        evidence=[EvidenceRef(claim="books via WhatsApp",
                              evidence=[EvidenceItem(page_url="https://brand.example",
                                                     quote="احجز على واتساب", extractor="rule:whatsapp_link")],
                              resolved=True)],
        kpi_target=KPITarget(metric="cost_per_lead", unit="EGP"),
        confidence=Confidence.HIGH, alternatives=[MetaObjective.TRAFFIC, MetaObjective.ENGAGEMENT])
    dumped = obj.model_dump()
    assert dumped["objective"] == "OUTCOME_LEADS"          # the API string, ready for Ads Manager
    assert dumped["destination"] == "whatsapp"
    restored = CampaignObjective.model_validate(dumped)
    assert restored == obj and restored.is_grounded is True
