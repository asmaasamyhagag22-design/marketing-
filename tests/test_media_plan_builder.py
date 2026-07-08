"""U1 Media Plan builder — the real U1 gate. Hermetic: MockCaller, no network.

The builder deduces objective + destination TOGETHER and grounds the destination in the brand's REAL
conversion surfaces. The contract these tests pin: a grounded surface -> a grounded objective; a
deduced destination with NO real signal -> an honest UNgrounded objective (never a fabricated store);
no caller / thin profile -> None.
"""
from __future__ import annotations

from business_profile.llm.caller import MockCaller
from media_plan.builder import build_campaign_objective, conversion_signals
from media_plan.schemas import (
    CampaignObjective, Destination, FunnelStage, MetaObjective, _COST_PER_RESULT_METRICS,  # noqa: F401
)
from media_plan.schemas import Confidence


def _ecom_profile():
    return {
        "name": {"value": "Oasis Store"}, "category": {"value": "ecommerce"},
        "description": {"value": "An online store selling home goods."},
        "source_url": "https://oasis.example/",
        "offerings": [{"name": "Sofa", "price_text": "EGP 5000", "page_url": "https://oasis.example/product/sofa"}],
        "contact_channels": {"whatsapp_numbers": [], "phones": [], "has_contact_form": False,
                             "physical_addresses": []},
    }


def _clinic_profile():
    return {
        "name": {"value": "Nasr City Clinic"}, "category": {"value": "clinic"},
        "description": {"value": "A dermatology clinic taking bookings on WhatsApp."},
        "source_url": "https://clinic.example/",
        "offerings": [{"name": "Consultation", "price_text": None, "page_url": None}],
        "contact_channels": {"whatsapp_numbers": ["+201000000000"], "phones": [],
                             "has_contact_form": True, "physical_addresses": ["Nasr City, Cairo"]},
    }


def _dedux(objective, destination, stage=FunnelStage.BOFU, conf=Confidence.HIGH, alts=None):
    from media_plan.builder import _ObjectiveDeduction
    return _ObjectiveDeduction(objective=objective, destination=destination, funnel_stage=stage,
                               rationale="grounded reason", confidence=conf, alternatives=alts or [])


def test_conversion_signals_reads_real_surfaces_only():
    # ecom: an online_store signal + website; NO whatsapp/phone (none in the profile)
    names = {n for n, _d, _r in conversion_signals(_ecom_profile())}
    assert "online_store" in names and "website" in names
    assert "whatsapp" not in names
    # clinic: whatsapp + contact_form + address + website; NO online_store
    cnames = {n for n, _d, _r in conversion_signals(_clinic_profile())}
    assert {"whatsapp", "contact_form", "address", "website"} <= cnames
    assert "online_store" not in cnames
    # every signal is resolved (a real structural fact, grounded by construction)
    assert all(ref.is_grounded for _n, _d, ref in conversion_signals(_clinic_profile()))


def test_store_brand_deduces_grounded_sales_objective():
    caller = MockCaller({"media_plan_objective": _dedux(MetaObjective.SALES, Destination.ONLINE_STORE,
                                                        alts=[MetaObjective.TRAFFIC])})
    obj = build_campaign_objective(_ecom_profile(), caller=caller)
    assert isinstance(obj, CampaignObjective)
    assert obj.objective is MetaObjective.SALES and obj.destination is Destination.ONLINE_STORE
    assert obj.budget_allocation_pct == 100.0
    assert obj.is_grounded is True                      # the store signal backs it
    assert obj.evidence[0].evidence[0].extractor == "rule:online_store"


def test_lead_brand_deduces_grounded_leads_objective():
    caller = MockCaller({"media_plan_objective": _dedux(MetaObjective.LEADS, Destination.WHATSAPP)})
    obj = build_campaign_objective(_clinic_profile(), caller=caller)
    assert obj.objective is MetaObjective.LEADS and obj.destination is Destination.WHATSAPP
    assert obj.is_grounded is True                      # the WhatsApp signal backs it


def test_deduced_destination_without_a_signal_is_honestly_ungrounded_not_fabricated():
    # the model picks SALES -> ONLINE_STORE for a clinic that has NO store. We do NOT invent a store;
    # the objective comes back UNgrounded (the advisor flags it), never a fabricated surface.
    caller = MockCaller({"media_plan_objective": _dedux(MetaObjective.SALES, Destination.ONLINE_STORE)})
    obj = build_campaign_objective(_clinic_profile(), caller=caller)
    assert obj is not None
    assert obj.is_grounded is False
    assert obj.evidence[0].resolved is False and obj.evidence[0].evidence == []


def test_no_caller_degrades_to_none(monkeypatch):
    for k in ("GOOGLE_CLOUD_PROJECT", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert build_campaign_objective(_ecom_profile()) is None


def test_thin_profile_with_no_surface_returns_none():
    caller = MockCaller({"media_plan_objective": _dedux(MetaObjective.AWARENESS, Destination.WEBSITE)})
    thin = {"name": {"value": "X"}}                     # no source_url, no offerings, no contact
    assert build_campaign_objective(thin, caller=caller) is None    # nothing to ground -> honest None


def test_website_only_brand_can_still_ground_traffic():
    caller = MockCaller({"media_plan_objective": _dedux(MetaObjective.TRAFFIC, Destination.WEBSITE,
                                                        stage=FunnelStage.TOFU)})
    prof = {"name": {"value": "New Co"}, "category": {"value": "services_b2b"},
            "source_url": "https://newco.example/", "offerings": [],
            "contact_channels": {"whatsapp_numbers": [], "phones": [], "has_contact_form": False,
                                 "physical_addresses": []}}
    obj = build_campaign_objective(prof, caller=caller)
    assert obj.objective is MetaObjective.TRAFFIC and obj.is_grounded is True   # the live site backs it
