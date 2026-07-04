"""Per-run COPYWRITING variation + research-fed concept (owner: "طريقة الكتابة ثابتة").

Hermetic. The design varied per run but the copy kept ONE rhetorical formula
(hook + proof + chips) — these pin the new copy-style axes + the research wiring:
  * build_variation carries copy_form/copy_voice (seed-deterministic);
  * the copy-style cue reaches the CONCEPT prompt;
  * research facts reach the prompt AND the grounding ledger (a research-sourced
    number in the copy RESOLVES instead of being blanked).
"""
from __future__ import annotations

from poster.brand_research import BrandFact, BrandResearch
from poster.concept import _ConceptResponse, build_creative_concept
from poster.variation import build_variation, copy_style_cue


def test_variation_carries_copy_axes_deterministically():
    v1, v2 = build_variation(seed=7), build_variation(seed=7)
    assert v1["copy_form"] == v2["copy_form"] and v1["copy_voice"] == v2["copy_voice"]
    cue = copy_style_cue(v1)
    assert "COPYWRITING STYLE" in cue and v1["copy_voice"] in cue
    # Different seeds explore different forms (at least somewhere in a small range).
    forms = {build_variation(seed=s)["copy_form"] for s in range(10)}
    assert len(forms) > 1
    assert copy_style_cue(None) == ""


class _CapturingCaller:
    def __init__(self, resp):
        self.resp, self.system, self.user = resp, "", ""

    def __call__(self, system, user, response_model, group_name=""):
        self.system, self.user = system, user
        return self.resp, None


_PROFILE = {
    "name": {"value": "Daturial", "evidence": [
        {"block_id": "b", "page_url": "https://daturial.example/", "quote": "Daturial"}]},
    "languages": ["en"],
    "tagline": {"value": "Autonomous AI Systems", "evidence": [
        {"block_id": "b2", "page_url": "https://daturial.example/", "quote": "Autonomous AI Systems"}]},
    "offerings": [],
}


def _resp(**kw) -> _ConceptResponse:
    base = dict(audience="enterprises", single_message="msg", core_benefit="benefit",
                emotional_tone="confident", visual_idea="scene", proof_points=[],
                headline="Delegate the work", subheadline="AI workers on your team",
                cta="Book a call")
    base.update(kw)
    return _ConceptResponse(**base)


def test_copy_style_cue_reaches_the_concept_prompt():
    caller = _CapturingCaller(_resp())
    v = build_variation(seed=3)
    build_creative_concept(_PROFILE, caller=caller, variation=v)
    assert "COPYWRITING STYLE" in caller.user
    assert v["copy_voice"] in caller.user


def test_research_facts_reach_prompt_and_ground_the_ledger():
    research = BrandResearch(used=True, facts=[
        BrandFact(text="Trains 5000 engineers annually",
                  source_url="https://news.example/daturial"),
    ])
    # The concept quotes the research number -> with research in the ledger it must
    # SURVIVE the grounding gate (before this wiring it would be blanked/softened).
    caller = _CapturingCaller(_resp(subheadline="5000 engineers trained annually"))
    c = build_creative_concept(_PROFILE, caller=caller, research=research,
                               enforce_grounding=True, max_retries=0)
    assert "FRESH SOURCED FACTS" in caller.user
    assert "5000" in caller.user and "news.example" in caller.user
    assert "5000" in c.subheadline          # research-sourced claim kept, not blanked


def test_research_absent_keeps_old_behavior():
    caller = _CapturingCaller(_resp())
    build_creative_concept(_PROFILE, caller=caller)
    assert "FRESH SOURCED FACTS" not in caller.user
