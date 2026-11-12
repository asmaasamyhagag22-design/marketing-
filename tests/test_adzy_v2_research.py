from datetime import datetime

import pytest

from strategy.campaign_research import Page, ResearchGap, parse_offer, research
from workflows.v2_cases import NAME, NOW, ROOT, home, offer_page

now = datetime.fromisoformat(NOW)


def test_guided_visits_terms_within_same_budget():
    def load(url, timeout):
        body = {ROOT: home(["contact", "terms"]), ROOT + "terms": offer_page()}
        return Page(url, body.get(url, b"<html><body>Contact</body></html>"))

    guided = research(ROOT, NAME, load, now=now)
    fixed = research(ROOT, NAME, load, now=now, method="fixed")
    assert guided["status"] == "READY" and fixed["status"] == "BUDGET_EXHAUSTED"
    assert guided["page_calls"] == fixed["page_calls"] == 2
    assert guided["trace"][1]["reason"] == "GAP_MATCH"
    assert guided["offer"]["page_url"] == ROOT + "terms"


@pytest.mark.parametrize(("overrides", "code"), [
    ({"extra": "<p>عرض عطلة الأسبوع مختلف.</p>"}, "UNPARSED_OFFER_CONTEXT"),
    ({"ends": "2026-11-11T23:59:00+02:00"}, "OFFER_EXPIRED"),
    ({"ends": "2026-11-30T23:59:00"}, "EXPLICIT_EXPIRY_OFFSET_REQUIRED"),
    ({"price": "40-60"}, "EXACT_PRICE_REQUIRED"),
    ({"name": "عرض مختلف"}, "OFFER_NAME_MISMATCH"),
])
def test_research_does_not_turn_partial_or_expired_evidence_into_offer(overrides, code):
    with pytest.raises(ResearchGap, match=code):
        parse_offer(Page(ROOT, offer_page(**overrides)), NAME, now)


def test_offsite_links_are_never_dispatched():
    calls = []

    def load(url, timeout):
        calls.append(url)
        return Page(url, b'<html><body><a href="http://127.0.0.1/terms">Terms</a></body></html>')

    result = research(ROOT, NAME, load, now=now)
    assert calls == [ROOT] and result["status"] == "NO_SUPPORTED_OFFER"
    assert result["next_action"] == "ASK_OWNER_FOR_DEDICATED_TERMS_PAGE"
