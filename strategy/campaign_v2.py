"""Evidence-bound campaign proposal, localized creative, and source revalidation."""
from datetime import datetime
from hashlib import sha256
import json

from strategy.campaign_research import ResearchGap, parse_offer, same_source, unparsed_excerpt, MAX_SECONDS


class CampaignConflict(Exception):
    def __init__(self, code, context=None):
        super().__init__(code)
        self.context = context or {}


class CampaignNotFound(Exception):
    pass


IMPACTS = {
    "name": "عرض الحملة وعنوان الإعلان",
    "price": "رسالة السعر في الاستراتيجية والإعلان",
    "priceCurrency": "عملة السعر في الاستراتيجية والإعلان",
    "availableAtOrFrom": "نطاق الفرع في الاستراتيجية والإعلان",
    "validThrough": "صلاحية العرض والإعلان",
    "description": "شروط العرض في الاستراتيجية والإعلان",
}


def compile_copy(offer):
    fields = offer["fields"]
    expiry = datetime.fromisoformat(offer["expires_at"])
    offset = expiry.strftime("%z")
    return {
        "headline": f"اطّلع على عرض {fields['name']}",
        "price": f"{fields['price']} {fields['priceCurrency']}",
        "branch": fields["availableAtOrFrom"],
        "validity": f"{expiry:%Y-%m-%d %H:%M:%S} (UTC{offset[:3]}:{offset[3:]})",
        "terms": fields["description"],
        "cta": "اطّلع على العرض وشروط الحجز",
    }


def creative(offer, brand_name):
    payload = {"layout": "arabic-offer-card@1", "language": "ar", "copy": compile_copy(offer),
               "evidence_sha256": offer["sha256"], "page_url": offer["page_url"], "brand_name": brand_name}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return {**payload, "sha256": sha256(encoded).hexdigest()}


def propose(name, outcome, *, brand_name="", booking_target=None, changes=(), watch_url=None):
    offer = outcome["offer"]
    return {
        "schema_version": 1,
        "status": "READY" if offer else "BLOCKED",
        "goal": "زيادة حجوزات الجلسة التجريبية",
        "booking_target": booking_target,
        "brand_name": brand_name,
        "offer_name": name,
        "research": outcome,
        "offer": offer,
        "watch_url": offer["page_url"] if offer else watch_url,
        "strategy": {
            "objective_type": "TRIAL_BOOKINGS",
            "recommendation": "اعرض السعر والفرع والشروط، ثم وجّه المهتم إلى صفحة العرض وشروط الحجز.",
            "assumption": "نفترض أن العرض يصلح لجذب حجوزات التجربة وأن وضوح الشروط يقلّل التردد. راجع ملاءمة العرض قبل الاعتماد.",
            "alternative": "إعلان تعريفي عن الجلسة يقود إلى صفحة البرنامج من دون إبراز عرض سعري.",
            "tradeoff": "الإعلان السعري أوضح في لحظة القرار ويحتاج تحديثًا عند تغيّر شروط العرض.",
            "metric": "عدد الحجوزات المكتملة للجلسة التجريبية",
        } if offer else None,
        "creative": creative(offer, brand_name) if offer else None,
        "changes": list(changes),
    }


def inactive_reason(result, now):
    offer = result.get("offer")
    if not offer:
        return "EVIDENCE_GAP"
    if now >= datetime.fromisoformat(offer["expires_at"]):
        return "OFFER_EXPIRED"
    if result.get("creative") != creative(offer, result["brand_name"]):
        return "CREATIVE_BINDING_CHANGED"
    return None


def refresh(result, loader, clock):
    """Check the approved evidence URL. A new observation yields a new proposal."""
    source = result["watch_url"]
    previous = result.get("offer")
    page = None
    try:
        page = loader(source, MAX_SECONDS)
        if page.url != source or not same_source(page.url, source):
            raise ResearchGap("SOURCE_URL_CHANGED")
        current = parse_offer(page, result["offer_name"], clock()).as_dict()
        if previous and current["sha256"] == previous["sha256"]:
            return None
    except (OSError, ResearchGap) as exc:
        code = str(exc) if isinstance(exc, ResearchGap) else "SOURCE_UNAVAILABLE"
        change = {"field": "validThrough" if code == "OFFER_EXPIRED" else "source",
                  "before": previous["expires_at"] if previous and code == "OFFER_EXPIRED" else source,
                  "after": code, "affects": "الاستراتيجية والإعلان السابقان",
                  "before_sha256": previous["sha256"] if previous else None,
                  "after_sha256": sha256(page.body).hexdigest() if page is not None else None}
        if code == "UNPARSED_OFFER_CONTEXT" and page is not None:
            change["observed_excerpt"] = unparsed_excerpt(page)
        return _revision(result, None, code, [change])

    old_fields = previous["fields"] if previous else {}
    changes = [
        {"field": field, "before": old_fields.get(field), "after": value, "affects": IMPACTS[field]}
        for field, value in current["fields"].items() if old_fields.get(field) != value
    ]
    if not changes:
        changes = [{"field": "source", "before": previous["sha256"], "after": current["sha256"],
                    "affects": "سياق الدليل المستخدم في الاستراتيجية والإعلان"}]
    return _revision(result, current, "SUPPORTED_OFFER", changes)


def _revision(result, offer, code, changes):
    source = result["watch_url"]
    outcome = {"status": "READY" if offer else "NO_SUPPORTED_OFFER", "offer": offer,
               "questions": result["research"].get("questions", []),
               "trace": [{"page_url": source, "reason": "RECHECK_BOUND_EVIDENCE", "outcome": code}],
               "page_calls": 1, "provider_calls": 0,
               "next_action": None if offer else "ASK_OWNER_FOR_DEDICATED_TERMS_PAGE"}
    return propose(result["offer_name"], outcome, brand_name=result["brand_name"],
                   booking_target=result.get("booking_target"), changes=changes, watch_url=source)
