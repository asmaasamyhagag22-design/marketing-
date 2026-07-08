"""U1 Media Plan — the builder (the real U1 gate).

`build_campaign_objective(profile, caller)` deduces the ONE objective + destination a brand should
run, TOGETHER, from the brand's real evidence — then grounds the choice in the actual conversion
surfaces the scrape found (a WhatsApp number, a checkout, a phone, an address). The LLM reasons
about WHICH objective; the code supplies + verifies the EVIDENCE. So a deduced destination is only
"grounded" when a real signal backs it — and a brand with no conversion surface yields an honest,
ungrounded objective (flagged downstream for the advisor), never a fabricated store.

Offline-testable: pass a MockCaller. No caller / creds -> None (honest-degrade, like the other
builders). PD-4: this module never hits the network itself.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from pydantic import BaseModel, Field

from business_profile.schemas import Confidence, EvidenceItem

from .schemas import CampaignObjective, Destination, EvidenceRef, FunnelStage, MetaObjective

logger = logging.getLogger(__name__)

_ECOM_CATEGORIES = {"ecommerce", "retail"}
_ECOM_URL_HINTS = ("cart", "checkout", "/product", "/products", "/shop", "/collections", "add-to-cart")


# ---------------------------------------------------------------------
# tolerant profile access (handles the object profile, the serialized dict,
# and the {"profile": {...}} wrapper — same discipline as the other builders)
# ---------------------------------------------------------------------

def _root(profile: Any) -> Any:
    if isinstance(profile, dict) and "profile" in profile and isinstance(profile["profile"], dict):
        return profile["profile"]
    return profile


def _get(obj: Any, key: str, default: Any = None) -> Any:
    val = obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
    return default if val is None else val


def _fv(obj: Any, key: str) -> str:
    """A scalar field value, unwrapping EvidencedField (object .value or {"value": ...})."""
    v = _get(obj, key)
    if isinstance(v, dict) and "value" in v:
        v = v.get("value")
    v = getattr(v, "value", v)
    return str(v).strip() if v else ""


def _offerings(profile: Any) -> List[dict]:
    out = []
    for o in (_get(profile, "offerings", []) or []):
        name = o.get("name") if isinstance(o, dict) else getattr(o, "name", None)
        price = o.get("price_text") if isinstance(o, dict) else getattr(o, "price_text", None)
        url = o.get("page_url") if isinstance(o, dict) else getattr(o, "page_url", None)
        out.append({"name": name, "price_text": price, "page_url": url})
    return out


def _contact(profile: Any) -> Any:
    return _get(profile, "contact_channels")


# ---------------------------------------------------------------------
# Conversion-surface signals — the grounding substrate for the destination
# ---------------------------------------------------------------------

def _ref(claim: str, url: str, quote: str, extractor: str) -> EvidenceRef:
    """A RESOLVED evidence ref — the signal is a real structural fact from the scrape, so it is
    grounded by construction (the code found it; the model did not assert it)."""
    return EvidenceRef(claim=claim, resolved=True,
                       evidence=[EvidenceItem(page_url=url or "", quote=(quote or "")[:200] or None,
                                              extractor=extractor)])


def conversion_signals(profile: Any) -> List[Tuple[str, Destination, EvidenceRef]]:
    """Every REAL conversion surface the scrape found, each paired with the Destination it enables
    and the resolved evidence that proves it. This is the ground truth the objective is anchored to;
    the deduction may only pick a destination that appears here."""
    p = _root(profile)
    src = _fv(p, "source_url") or _fv(p, "url") or _fv(p, "website") or ""
    out: List[Tuple[str, Destination, EvidenceRef]] = []

    cc = _contact(p)
    whatsapp = list(_get(cc, "whatsapp_numbers", []) or []) if cc is not None else []
    phones = list(_get(cc, "phones", []) or []) if cc is not None else []
    has_form = bool(_get(cc, "has_contact_form", False)) if cc is not None else False
    addresses = list(_get(cc, "physical_addresses", []) or []) if cc is not None else []

    if whatsapp:
        out.append(("whatsapp", Destination.WHATSAPP,
                    _ref("the brand takes contact/orders via WhatsApp", src, str(whatsapp[0]), "rule:whatsapp")))
    if phones:
        num = getattr(phones[0], "raw", None) or (phones[0].get("raw") if isinstance(phones[0], dict) else str(phones[0]))
        out.append(("phone", Destination.PHONE_CALL,
                    _ref("the brand publishes a phone line to call", src, str(num), "rule:tel_link")))
    if has_form:
        out.append(("contact_form", Destination.LEAD_FORM,
                    _ref("the site has a contact/booking form", src, "contact form", "rule:contact_form")))
    if addresses:
        out.append(("address", Destination.PHYSICAL_STORE,
                    _ref("the brand has a physical location", src, str(addresses[0]), "rule:address")))

    # online store: an ecommerce/retail category, OR a priced offering on a cart/shop URL
    category = _fv(p, "category").lower()
    store_url, store_quote = "", ""
    for off in _offerings(p):
        url = (off.get("page_url") or "")
        if off.get("price_text") and (any(h in url.lower() for h in _ECOM_URL_HINTS) or category in _ECOM_CATEGORIES):
            store_url, store_quote = url or src, f"{off.get('name')} — {off.get('price_text')}"
            break
    if store_url or category in _ECOM_CATEGORIES:
        out.append(("online_store", Destination.ONLINE_STORE,
                    _ref("the brand sells products through an online store", store_url or src,
                         store_quote or category, "rule:online_store")))

    # the website itself always exists when we scraped one — a grounded baseline for TRAFFIC/AWARENESS
    if src:
        out.append(("website", Destination.WEBSITE,
                    _ref("the brand has a live website", src, src, "rule:source_url")))
    return out


# ---------------------------------------------------------------------
# The deduction (LLM) + assembly
# ---------------------------------------------------------------------

class _ObjectiveDeduction(BaseModel):
    """What the model returns: WHICH objective, to WHICH available destination, and why."""
    objective: MetaObjective
    destination: Destination
    funnel_stage: FunnelStage
    rationale: str = ""
    confidence: Confidence = Confidence.NONE
    alternatives: List[MetaObjective] = Field(default_factory=list)


_SYSTEM = (
    "You are a senior Meta media-buying strategist. Deduce the ONE campaign objective a brand should "
    "run FIRST, and the destination it drives to — TOGETHER, from the brand's real facts.\n"
    "HARD RULES:\n"
    "- Pick exactly one MetaObjective and one Destination.\n"
    "- The Destination MUST be one of the AVAILABLE conversion surfaces listed below — never invent a "
    "surface the brand doesn't have (no 'Sales / online store' if there is no store).\n"
    "- Match the objective to the surface: a real online store -> Sales; bookings/leads via "
    "WhatsApp/phone/form -> Leads; only a website and no conversion surface -> Traffic or Awareness.\n"
    "- rationale: ONE sentence, grounded in the facts + the chosen surface. Invent no numbers, "
    "claims, or guarantees.\n"
    "- funnel_stage: the stage this single objective serves (a one-objective plan is a complete "
    "single-stage funnel — usually BOFU for a conversion goal, TOFU for pure awareness)."
)


def _deduce_user(profile: Any, signals: List[Tuple[str, Destination, EvidenceRef]]) -> str:
    p = _root(profile)
    offers = [o["name"] for o in _offerings(p) if o.get("name")][:8]
    surfaces = "\n".join(f"- {name} -> Destination '{dest.value}'" for name, dest, _ in signals)
    return (
        f"Brand: {_fv(p, 'name')}\n"
        f"Category: {_fv(p, 'category') or 'unknown'}\n"
        f"What they do: {_fv(p, 'description')[:400]}\n"
        + (f"Offerings: {', '.join(offers)}\n" if offers else "")
        + f"AVAILABLE conversion surfaces (pick the Destination from THESE only):\n{surfaces}\n"
        + "\nReturn the deduced objective, destination, funnel_stage, rationale, confidence, alternatives."
    )


def _ground_destination(dest: Destination,
                        signals: List[Tuple[str, Destination, EvidenceRef]]) -> EvidenceRef:
    """The resolved evidence for the chosen destination — or, if the model picked a destination the
    brand has NO signal for, an UNRESOLVED ref (honest ungrounded output, flagged downstream). We
    never fabricate a signal that isn't in the scrape."""
    for _name, d, ref in signals:
        if d is dest:
            return ref
    return EvidenceRef(claim=f"targets destination '{dest.value}' (no matching conversion surface found)",
                       evidence=[], resolved=False)


def build_campaign_objective(profile: Any, caller: Any = None) -> Optional[CampaignObjective]:
    """Deduce the single grounded CampaignObjective for a brand. None on honest-degrade (no caller /
    creds, or a profile too thin to expose ANY surface). An objective whose destination lacks a real
    signal comes back with `is_grounded == False` — a valid honest output the advisor flags, not a
    fabricated one. `caller` is injectable for tests; defaults to default_caller(strong=True)."""
    if caller is None:
        from business_profile.llm import default_caller
        caller = default_caller(strong=True)
    if caller is None:
        logger.info("media_plan: no Gemini caller (creds/SDK); skipping objective deduction")
        return None

    signals = conversion_signals(profile)
    if not signals:
        logger.info("media_plan: no conversion surface / website found; too thin to deduce")
        return None

    try:
        dedux, _usage = caller(_SYSTEM, _deduce_user(profile, signals), _ObjectiveDeduction,
                               group_name="media_plan_objective")
    except Exception as e:  # noqa: BLE001 — a call failure must never crash the plan
        logger.warning("media_plan: objective deduction failed: %s", e)
        return None

    return CampaignObjective(
        objective=dedux.objective,
        destination=dedux.destination,
        funnel_stage=dedux.funnel_stage,
        rationale=(dedux.rationale or "").strip() or "(no rationale returned)",
        budget_allocation_pct=100.0,                     # single objective -> the whole budget
        evidence=[_ground_destination(dedux.destination, signals)],
        confidence=dedux.confidence,
        alternatives=list(dedux.alternatives)[:3],
    )
