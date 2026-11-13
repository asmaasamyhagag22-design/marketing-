from datetime import datetime, timezone

import pytest

from strategy.campaign_planner import BriefReview, PlanInput, build_plan, review_draft
from strategy.campaign_research import Page
from strategy.campaign_v2 import CampaignConflict


def make_draft(quote, language, topic, context=None):
    url = "https://publisher.example/features"
    html = f"<html><head><title>{topic}</title></head><body><main><h1>{topic}</h1><p>{context or quote}</p></main></body></html>"
    request = PlanInput(url=url, objective=f"Increase visits to the {topic} explanation", language=language)
    return build_plan(request, "Publisher", lambda url, timeout: Page(url, html.encode()),
                      lambda: datetime.now(timezone.utc))


def review(draft, **edits):
    brief = draft["brief"]
    direction = brief["directions"][brief["selected"]]
    copy = {key: direction[key] for key in ("headline", "message", "cta", "caption")}
    return review_draft(draft, BriefReview(audience=brief["audience"], tone=brief["tone"],
                                          selected=brief["selected"], copy_edit={**copy, **edits}))


def test_known_tracker_scope_survives_valid_rewrite_and_rejects_expansion():
    draft = make_draft("The browser blocks thousands of known trackers while you browse.", "ar", "Known Trackers")
    exact = review(draft)
    new = review(draft, message="يحجب المتصفّح آلاف المتعقّبات المعروفة أثناء التصفّح.")
    assert exact["sha256"] != new["sha256"]
    assert new["evidence"] == draft["evidence"]
    assert "المعروفة" in new["package"]["copy"]["message"]
    assert new["package"]["concept"] == "filter"
    for edits in ({"message": "يحجب المتصفّح كل المتعقّبات."},
                  {"headline": "تصفح بأمان تام"}, {"cta": "نزّل الآن"}):
        with pytest.raises(CampaignConflict, match="COPY_REQUIRES_EVIDENCE_REVIEW"):
            review(draft, **edits)


def test_model_comparator_rewrite_passes_and_retains_bound_destination():
    draft = make_draft("Use the Comparator to place artworks side by side and zoom in on the smallest details.",
                       "en", "Artworks Comparator")
    result = review(draft, headline="Compare Artworks Side by Side",
                    message="Use the Comparator to place artworks next to each other and zoom in on the smallest details.")
    assert result["package"]["copy"]["headline"] == "Compare Artworks Side by Side"
    assert result["package"]["storyboard"][0]["line"] == "Compare Artworks Side by Side"
    assert result["package"]["source_url"] == draft["evidence"][0]["page_url"]
    with pytest.raises(CampaignConflict, match="COPY_REQUIRES_EVIDENCE_REVIEW"):
        review(draft, message="Compare every artwork from any museum side by side.")


def test_qualified_context_does_not_license_unconditional_copy():
    from strategy.campaign_copy import writing_for

    evidence = {"quote": "The browser blocks thousands of known trackers.",
                "context": "The browser blocks thousands of known trackers. This only applies when enabled."}
    assert writing_for(evidence, "READ_FEATURE", "ar") is None



def test_catalog_cta_requires_destination_and_does_not_guarantee_stock():
    from strategy.campaign_copy import writing_for

    quote = "Browse the pieces or search for a brick for your build."
    fact = {"quote": quote, "page_url": "https://publisher.example/articles/construction"}
    assert writing_for(fact, "READ_FEATURE", "ar") is None
    fact["page_url"] = "https://publisher.example/catalog"
    result = writing_for(fact, "READ_FEATURE", "ar")
    assert result.cta == "تصفّح القطع"
    assert not result.license("message", "كل القطع متوفرة في كل الفروع.")
