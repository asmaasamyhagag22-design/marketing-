"""TOWS synthesis (competitor/tows.py) — hermetic.

Proves the grounding discipline the port added over the team's original:
  * deterministic pairing: anchors valid BY CONSTRUCTION, text verbatim from cited items;
  * LLM path: a strategy citing an unknown anchor id is DROPPED;
  * Ledger gate: LLM strategy text carrying an unsourced falsifiable claim is replaced
    with the grounded template (the pairing survives, the fabrication doesn't);
  * standalone degrade: a SWOT with no O/T still yields a useful S/W priority plan;
  * claim_strength propagates as the WEAKEST anchored item's strength.
"""
from __future__ import annotations

from competitor.swot import SWOT, SWOTItem
from competitor.tows import build_tows, swot_item_ids


def _item(text, strength="validated"):
    return SWOTItem(text=text, citation=["your profile"], evidence=text,
                    claim_strength=strength)


def _full_swot() -> SWOT:
    return SWOT(
        strengths=[_item("Online booking present"), _item("Bilingual site")],
        weaknesses=[_item("No WhatsApp contact", strength="directional_not_validated")],
        opportunities=[_item("Peers all lack online booking")],
        threats=[_item("Your review volume is below the peer average")],
    )


class _FakeCaller:
    """Caller-protocol fake returning a canned _TowsResponse."""
    def __init__(self, strategies):
        self._strategies = strategies

    def __call__(self, system, user, response_model, group_name=""):
        resp = response_model(strategies=self._strategies)
        return resp, None


def test_deterministic_pairing_grounded_by_construction():
    swot = _full_swot()
    res = build_tows(swot)

    assert res.strategies, "a full SWOT must yield TOWS pairs"
    ids = swot_item_ids(swot)
    types = {s.type for s in res.strategies}
    assert {"SO", "ST", "WO", "WT"} <= types
    for s in res.strategies:
        assert s.anchors and all(a in ids for a in s.anchors)
        # Template text quotes the cited items verbatim — grounded by construction.
        assert any(ids[a].text in s.description for a in s.anchors)
    assert res.priority_actions
    assert res.priority_actions[0].horizon == "now"   # SO ranks first


def test_llm_strategy_with_unknown_anchor_is_dropped():
    swot = _full_swot()
    caller = _FakeCaller([
        {"type": "SO", "title": "Good pairing", "description": "Use booking to win.",
         "anchors": ["S1", "O1"]},
        {"type": "ST", "title": "Invented anchor", "description": "x",
         "anchors": ["S1", "T9"]},   # T9 doesn't exist
    ])
    res = build_tows(swot, caller=caller)

    assert [s.title for s in res.strategies] == ["Good pairing"]
    assert any("unknown anchors" in n for n in res.notes)


def test_llm_fabricated_claim_is_replaced_with_grounded_template():
    swot = _full_swot()
    # Profile evidence knows nothing about "#1" / awards.
    profile = {
        "name": {"value": "Clinic", "evidence": [
            {"block_id": "b", "page_url": "https://clinic.example/", "quote": "Clinic"}]},
    }
    caller = _FakeCaller([
        {"type": "SO", "title": "Ride the #1 clinic award",
         "description": "As the award-winning #1 clinic since 1990, expand booking.",
         "anchors": ["S1", "O1"]},
    ])
    res = build_tows(swot, caller=caller, profile=profile)

    assert len(res.strategies) == 1
    s = res.strategies[0]
    assert s.source == "llm_text_replaced"
    assert "#1" not in s.title and "#1" not in s.description
    assert "1990" not in s.description
    assert "Online booking present" in s.description     # the grounded template
    assert s.anchors == ["S1", "O1"]                       # the pairing survived


def test_standalone_swot_still_yields_priority_actions():
    swot = SWOT(
        strengths=[_item("Social links: 6", strength="internally_supported")],
        weaknesses=[_item("Online booking: not detected", strength="internally_supported")],
        mode="standalone",
    )
    res = build_tows(swot)

    assert res.strategies == []                    # no O/T -> no pairs, honestly
    assert res.priority_actions, "S/W must still produce a plan"
    assert any(a.action.startswith("Fix:") for a in res.priority_actions)
    assert any(a.action.startswith("Double down:") for a in res.priority_actions)
    assert res.posture == "improvement"


def test_claim_strength_is_weakest_anchor_and_empty_swot_safe():
    swot = _full_swot()
    res = build_tows(swot)
    wo = [s for s in res.strategies if s.type == "WO"]
    assert wo and wo[0].claim_strength == "directional_not_validated"  # W1 is directional

    empty = build_tows(SWOT())
    assert empty.strategies == [] and empty.priority_actions == []
    assert any("no items" in n for n in empty.notes)
