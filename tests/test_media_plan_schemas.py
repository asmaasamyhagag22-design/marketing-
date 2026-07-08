"""U1 Media Plan — core schema contracts. Hermetic (no network, no LLM).

Pins the frozen facts + every validator a downstream unit (builder, launch bundle, defense) relies
on: exactly six Meta objectives; strict models; the funnel/budget layer sums to 100; the learning
floor; grounded = weakest-link; persona/geo grounding.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from business_profile.schemas import Confidence, EvidenceItem
from media_plan.schemas import (
    CampaignObjective, Destination, EvidenceRef, FunnelStage, GeoMode, GeoTargeting,
    KPITarget, MediaPlan, MetaObjective, Persona,
)


def _ev(quote="Add to cart", extractor="rule:cart_link") -> EvidenceItem:
    return EvidenceItem(page_url="https://brand.example/shop", quote=quote, extractor=extractor)


def _ref(claim="sells online", resolved=True) -> EvidenceRef:
    return EvidenceRef(claim=claim, evidence=[_ev()], resolved=resolved)


def _obj(objective=MetaObjective.SALES, stage=FunnelStage.BOFU, pct=100.0,
         dest=Destination.ONLINE_STORE, grounded=True, **kw) -> CampaignObjective:
    return CampaignObjective(objective=objective, destination=dest, funnel_stage=stage,
                             rationale="grounded reason", budget_allocation_pct=pct,
                             evidence=[_ref(resolved=grounded)], **kw)


def _persona() -> Persona:
    return Persona(age_range=_ref(claim="25-34"), interests=[_ref(claim="fitness")])


def _geo() -> GeoTargeting:
    return GeoTargeting(mode=GeoMode.NATIONAL)


# --- objectives -------------------------------------------------------------

def test_there_are_exactly_six_meta_objectives_with_odax_api_values():
    assert len(MetaObjective) == 6
    assert {o.value for o in MetaObjective} == {
        "OUTCOME_AWARENESS", "OUTCOME_TRAFFIC", "OUTCOME_ENGAGEMENT",
        "OUTCOME_LEADS", "OUTCOME_APP_PROMOTION", "OUTCOME_SALES"}
    assert MetaObjective.SALES.value == "OUTCOME_SALES" and MetaObjective.LEADS.label == "Leads"


def test_campaign_objective_is_strict_and_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        _obj(objectiv=MetaObjective.LEADS)                     # typo'd field -> loud fail


def test_allocation_pct_is_bounded_0_to_100():
    with pytest.raises(ValidationError):
        _obj(pct=140.0)
    with pytest.raises(ValidationError):
        _obj(pct=-1.0)


def test_objective_is_grounded_only_when_evidence_resolves():
    assert _obj(grounded=True).is_grounded is True
    assert _obj(grounded=False).is_grounded is False          # unresolved ref = hypothesis, not fact


def test_learning_floor_enforced_only_when_budget_and_target_known():
    kpi = KPITarget(metric="cost_per_lead", target_value=50.0, unit="EGP")
    # floor = 3 * 50 * 2 ad sets = 300; 250 fails, 300 passes
    with pytest.raises(ValidationError):
        _obj(kpi_target=kpi, num_ad_sets=2, test_budget=250.0)
    ok = _obj(kpi_target=kpi, num_ad_sets=2, test_budget=300.0)
    assert ok.test_budget == 300.0
    # honest-unknown: no target OR no test_budget -> the floor is not asserted (never a fake pass)
    assert _obj(kpi_target=KPITarget(metric="reach"), test_budget=1.0).test_budget == 1.0
    assert _obj(test_budget=1.0).test_budget == 1.0


# --- media plan (the funnel/budget layer) -----------------------------------

def test_single_objective_plan_auto_resolves_allocation_to_100():
    # trap 3: one objective is fully valid; the caller shouldn't have to type 100.
    plan = MediaPlan(run_id="r1", market_definition_ref="md1",
                     objectives=[_obj(pct=0.0)], base_persona=_persona(), base_geo=_geo())
    assert plan.objectives[0].budget_allocation_pct == 100.0
    assert plan.is_grounded is True


def test_multi_objective_allocations_must_sum_to_100():
    good = MediaPlan(run_id="r", market_definition_ref="md", base_persona=_persona(), base_geo=_geo(),
                     objectives=[_obj(MetaObjective.TRAFFIC, FunnelStage.TOFU, 60.0, Destination.WEBSITE),
                                 _obj(MetaObjective.SALES, FunnelStage.BOFU, 40.0)])
    assert abs(sum(o.budget_allocation_pct for o in good.objectives) - 100.0) < 1e-9
    with pytest.raises(ValidationError):     # 60 + 30 = 90 != 100
        MediaPlan(run_id="r", market_definition_ref="md", base_persona=_persona(), base_geo=_geo(),
                  objectives=[_obj(MetaObjective.TRAFFIC, FunnelStage.TOFU, 60.0, Destination.WEBSITE),
                              _obj(MetaObjective.SALES, FunnelStage.BOFU, 30.0)])


def test_plan_grounded_is_weakest_link_all_objectives():
    # one ungrounded objective sinks the whole plan (as strong as the weakest link, not the strongest)
    plan = MediaPlan(run_id="r", market_definition_ref="md", base_persona=_persona(), base_geo=_geo(),
                     objectives=[_obj(MetaObjective.TRAFFIC, FunnelStage.TOFU, 50.0, Destination.WEBSITE,
                                      grounded=True),
                                 _obj(MetaObjective.SALES, FunnelStage.BOFU, 50.0, grounded=False)])
    assert plan.is_grounded is False


def test_plan_grounding_folds_in_persona_and_geo_not_just_objectives():
    # a plan with all-grounded objectives but a GUESSED persona is NOT grounded (the weakest link
    # is the audience, not the objective). Regression for the audit's confirmed is_grounded gap.
    p_guessed = MediaPlan(run_id="r", market_definition_ref="md", base_geo=_geo(),
                          base_persona=Persona(),                       # empty = a guess
                          objectives=[_obj(pct=100.0, grounded=True)])
    assert p_guessed.is_grounded is False

    # a RADIUS geo whose address is not Ledger-resolved also sinks it
    ungrounded_geo = GeoTargeting(mode=GeoMode.RADIUS, center_address="Nasr City", radius_km=8.0,
                                  address_ref=_ref(claim="addr", resolved=False))
    p_geo = MediaPlan(run_id="r", market_definition_ref="md", base_persona=_persona(),
                      base_geo=ungrounded_geo, objectives=[_obj(pct=100.0, grounded=True)])
    assert p_geo.is_grounded is False


def test_geo_modes_are_mutually_exclusive():
    for bad in (
        dict(mode=GeoMode.RADIUS, center_address="x", radius_km=5.0, cities=["Cairo"]),   # radius + cities
        dict(mode=GeoMode.CITIES, cities=["Cairo"], radius_km=5.0),                        # cities + radius
        dict(mode=GeoMode.REGIONS, regions=["Giza"], cities=["Cairo"]),                    # regions + cities
        dict(mode=GeoMode.NATIONAL, cities=["Cairo"]),                                     # national + cities
        dict(mode=GeoMode.NATIONAL, center_address="x", radius_km=5.0),                    # national + radius
    ):
        with pytest.raises(ValidationError):
            GeoTargeting(**bad)


def test_learning_floor_only_applies_to_cost_per_result_metrics():
    # a huge reach target must NOT be treated as a per-conversion cost (floor is meaningless there)
    reach = KPITarget(metric="reach", target_value=500000.0)
    ok = _obj(kpi_target=reach, num_ad_sets=3, test_budget=100.0)   # would be a giant floor if misapplied
    assert ok.test_budget == 100.0
    # but a cost-per-lead target DOES gate it
    cpl = KPITarget(metric="cost_per_lead", target_value=50.0, unit="EGP")
    with pytest.raises(ValidationError):
        _obj(kpi_target=cpl, num_ad_sets=2, test_budget=100.0)      # floor 300 > 100


def test_kpi_target_and_window_reject_nonpositive():
    with pytest.raises(ValidationError):
        KPITarget(metric="cpl", target_value=0.0)
    with pytest.raises(ValidationError):
        KPITarget(metric="cpl", target_value=-10.0)
    with pytest.raises(ValidationError):
        KPITarget(metric="reach", window_days=-7)


def test_media_plan_requires_at_least_one_objective():
    with pytest.raises(ValidationError):
        MediaPlan(run_id="r", market_definition_ref="md", objectives=[],
                  base_persona=_persona(), base_geo=_geo())


# --- persona + geo grounding ------------------------------------------------

def test_persona_grounded_only_when_every_asserted_axis_resolves():
    assert Persona().is_grounded is False                       # empty = not grounded (a guess)
    assert Persona(age_range=_ref(claim="25-34")).is_grounded is True
    # one ungrounded axis sinks it
    assert Persona(age_range=_ref(claim="25-34"),
                   gender=_ref(claim="women", resolved=False)).is_grounded is False


def test_geo_mode_field_consistency():
    assert GeoTargeting(mode=GeoMode.NATIONAL).mode is GeoMode.NATIONAL
    GeoTargeting(mode=GeoMode.RADIUS, center_address="Nasr City, Cairo", radius_km=10.0)
    for bad in (
        dict(mode=GeoMode.RADIUS, center_address="x"),                     # no radius_km
        dict(mode=GeoMode.RADIUS, center_address="x", radius_km=0.0),      # 0 km is nonsensical
        dict(mode=GeoMode.RADIUS, center_address="x", radius_km=-5.0),     # negative
        dict(mode=GeoMode.CITIES),                                         # no cities
        dict(mode=GeoMode.REGIONS),                                        # no regions
    ):
        with pytest.raises(ValidationError):
            GeoTargeting(**bad)


def test_test_budget_must_be_positive_when_provided():
    with pytest.raises(ValidationError):
        _obj(test_budget=-5.0)
    with pytest.raises(ValidationError):
        _obj(test_budget=0.0)


def test_plan_round_trips_through_json_with_api_objective_strings():
    plan = MediaPlan(run_id="run-1", market_definition_ref="md-oasis", base_persona=_persona(),
                     base_geo=GeoTargeting(mode=GeoMode.RADIUS, center_address="Nasr City", radius_km=8.0,
                                           address_ref=_ref(claim="Nasr City clinic")),
                     objectives=[_obj(MetaObjective.LEADS, FunnelStage.BOFU, 100.0, Destination.WHATSAPP,
                                      kpi_target=KPITarget(metric="cost_per_lead", unit="EGP"),
                                      confidence=Confidence.HIGH)])
    dumped = plan.model_dump()
    assert dumped["objectives"][0]["objective"] == "OUTCOME_LEADS"     # Ads-API string
    assert dumped["objectives"][0]["destination"] == "whatsapp"
    restored = MediaPlan.model_validate(dumped)
    assert restored == plan and restored.is_grounded is True
