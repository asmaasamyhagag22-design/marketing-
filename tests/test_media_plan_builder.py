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


def _priced(n, base="https://tasty.example", path=""):
    return [{"name": f"Item {i}", "price_text": f"EGP {50 + i}", "page_url": f"{base}{path}"}
            for i in range(n)]


def _catalog_profile(offerings, category="restaurant"):
    return {"name": {"value": "Tasty"}, "category": {"value": category},
            "description": {"value": "A brand with priced offerings."},
            "source_url": "https://tasty.example/", "offerings": offerings,
            "contact_channels": {"whatsapp_numbers": [], "phones": [], "has_contact_form": False,
                                 "physical_addresses": []}}


def test_priced_catalog_on_own_site_grounds_online_store():
    # FIX-1: >=3 priced offerings on the brand's OWN domain = a store surface, even with no
    # cart-ish URL and a non-ecom category (norshek: 12 priced on the homepage, category '')
    names = {n for n, _d, _r in conversion_signals(_catalog_profile(_priced(3), category=""))}
    assert "online_store" in names
    ref = next(r for n, _d, r in conversion_signals(_catalog_profile(_priced(3), category=""))
               if n == "online_store")
    assert ref.is_grounded and "3 priced offerings" in (ref.evidence[0].quote or "")


def test_order_and_menu_urls_count_as_store_hints():
    # FIX-1: a priced offering on an order/menu URL is a store even below the catalog threshold
    # (buffalo_burger: priced offerings on /menu)
    offs = _priced(1, path="/branches/all/menu")
    assert "online_store" in {n for n, _d, _r in conversion_signals(_catalog_profile(offs))}


def test_two_priced_offerings_stay_below_catalog_threshold():
    # a lone/duo price (e.g. a delivery fee) must NOT fabricate a store
    names = {n for n, _d, _r in conversion_signals(_catalog_profile(_priced(2)))}
    assert "online_store" not in names


def test_offsite_priced_offerings_do_not_count_toward_the_catalog():
    # 3 priced offerings that live on a MARKETPLACE domain are not the brand's own store
    offs = _priced(3, base="https://marketplace.example", path="/sellers/tasty")
    names = {n for n, _d, _r in conversion_signals(_catalog_profile(offs))}
    assert "online_store" not in names


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
