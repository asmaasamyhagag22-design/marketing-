"""H7 gate: `--trend` must actually reach the poster copy.

Regression origin (2026-07-05 audit): the trend titles were read ONLY inside the poster's
`--research and not headline_override` branch, so `--trend` was a guaranteed no-op on the
campaign dispatch path (which passes `--trend` but not `--research`, and `--from-plan` sets
a headline override). The fix threads a `trend_context` into the creative concept so a
dispatched poster genuinely rides a trend — while the grounding gate still protects every
claim (a trend is inspiration, never a licence to fabricate).

Hermetic: a mock caller captures the concept prompt; no network, no real LLM.
"""
from types import SimpleNamespace

from poster.concept import build_creative_concept


def _mock_caller(captured):
    resp = SimpleNamespace(
        audience="shoppers", single_message="Fresh looks", core_benefit="style",
        emotional_tone="confident", visual_idea="a bright studio scene",
        proof_points=["real feature A", "real feature B"],
        headline="Discover your style", subheadline="New spring pieces in store",
        cta="Visit the shop",
    )

    def caller(system, user, model, group_name=None):
        captured["system"] = system
        captured["user"] = user
        return resp, {}

    return caller


_PROFILE = {
    "name": {"value": "Elie Top"},
    "description": {"value": "A jewelry maison."},
    "offerings": [{"name": "Rings"}],
}


def test_trend_context_reaches_the_concept_prompt():
    cap = {}
    build_creative_concept(_PROFILE, caller=_mock_caller(cap),
                           trend_context="- Sustainable luxury 2026\n- Bold statement jewelry")
    assert "Sustainable luxury 2026" in cap["user"]
    assert "Bold statement jewelry" in cap["user"]
    assert "CURRENT TRENDS" in cap["user"]


def test_no_trend_context_no_trend_block():
    cap = {}
    build_creative_concept(_PROFILE, caller=_mock_caller(cap))
    assert "CURRENT TRENDS" not in cap["user"]


def test_empty_trend_context_is_ignored():
    cap = {}
    build_creative_concept(_PROFILE, caller=_mock_caller(cap), trend_context="   ")
    assert "CURRENT TRENDS" not in cap["user"]


def test_trend_block_keeps_the_no_fabrication_rule():
    cap = {}
    build_creative_concept(_PROFILE, caller=_mock_caller(cap),
                           trend_context="- AI everything")
    # The trend instruction must NOT license inventing facts to match a trend.
    assert "do NOT invent" in cap["user"]
    assert "proof must stay REAL" in cap["user"]


def test_generate_poster_accepts_trend_context_param():
    # Plumbing: the pipeline entrypoint exposes trend_context (forwarded to the concept).
    import inspect
    from poster.pipeline import generate_poster
    assert "trend_context" in inspect.signature(generate_poster).parameters
