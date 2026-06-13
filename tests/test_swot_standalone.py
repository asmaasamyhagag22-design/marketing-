"""Standalone SWOT degrade — no empty SWOT when competitors are missing.

When discovery finds 0 peers (or the comparison is too thin to clear the
evidence bar), synthesize_swot falls back to a profile-only analysis built from
the subject's OWN scraped dimensions. Grounded: every item is cited and UNKNOWN
(None) cells are skipped. Competitive mode is left unchanged.
"""
from __future__ import annotations

from competitor.matrix import (
    ComparativeGapMatrix, MatrixColumn, DimensionGap, Dimension,
)
from competitor.swot import synthesize_swot


def _subject():
    # real thehairaddict deduped dims; shows_reviews/trust_count are UNKNOWN
    return MatrixColumn(name="You", is_subject=True, values={
        "online_booking": False, "whatsapp": True, "shows_reviews": None,
        "cta_count": 2, "offerings_count": 10, "bilingual": False,
        "trust_count": None, "social_count": 1,
    })


def test_zero_peers_degrades_to_standalone():
    swot = synthesize_swot(ComparativeGapMatrix(columns=[_subject()], gaps=[]), themes=[])
    assert swot.mode == "standalone"
    assert any("WhatsApp" in s.text for s in swot.strengths)
    assert any("Online booking" in w.text for w in swot.weaknesses)
    assert any(n.startswith("Standalone Strategic Analysis (No Competitors") for n in swot.notes)


def test_standalone_is_never_empty_and_always_cited():
    swot = synthesize_swot(ComparativeGapMatrix(columns=[_subject()], gaps=[]), themes=[])
    assert swot.strengths or swot.weaknesses          # never empty
    for item in swot.strengths + swot.weaknesses:
        assert item.citation                          # every item traceable


def test_standalone_skips_unknown_cells_and_uses_deduped_counts():
    swot = synthesize_swot(ComparativeGapMatrix(columns=[_subject()], gaps=[]), themes=[])
    cited_keys = {c for it in swot.strengths + swot.weaknesses for c in it.citation}
    assert "shows_reviews" not in cited_keys          # UNKNOWN -> excluded (rule #4)
    assert "trust_count" not in cited_keys
    assert any("Social links: 1" in s.text for s in swot.strengths)  # deduped, not inflated


def test_competitive_mode_unchanged_when_gaps_exist():
    subj = _subject()
    peer = MatrixColumn(name="Peer", is_subject=False, values={"whatsapp": False})
    gap = DimensionGap(
        Dimension("whatsapp", "WhatsApp contact", "scraped", "bool", "higher_better"),
        subject_value=True, competitor_values={"Peer": False},
        verdict="ahead", detail="You have WhatsApp; Peer does not",
    )
    swot = synthesize_swot(ComparativeGapMatrix(columns=[subj, peer], gaps=[gap]), themes=[])
    assert swot.mode == "competitive"
    assert len(swot.strengths) == 1
    assert swot.strengths[0].text == "You have WhatsApp; Peer does not"


def test_scraped_behind_with_peers_yields_weakness_and_threat():
    # A web/SERP peer outperforming you on a SITE dimension is both an internal
    # weakness AND an external threat — this is what fills Threats for ECOMMERCE.
    subj = _subject()
    peer = MatrixColumn(name="Rival", is_subject=False, values={"whatsapp": True})
    gap = DimensionGap(
        Dimension("whatsapp", "WhatsApp contact", "scraped", "bool", "higher_better"),
        subject_value=False, competitor_values={"Rival": True},
        verdict="behind", detail="Rival has WhatsApp; you do not",
    )
    swot = synthesize_swot(ComparativeGapMatrix(columns=[subj, peer], gaps=[gap]), themes=[])
    assert swot.mode == "competitive"
    assert len(swot.weaknesses) == 1                          # internal lens kept
    assert len(swot.threats) == 1                             # NEW external lens
    assert "WhatsApp contact" in swot.threats[0].text
    assert any("Rival" in c for c in swot.threats[0].citation)  # grounded in the peer


def test_scraped_behind_standalone_emits_no_phantom_threat():
    # 0 peers -> standalone -> the competitive threat must NOT fire.
    subj = _subject()
    swot = synthesize_swot(ComparativeGapMatrix(columns=[subj], gaps=[]), themes=[])
    assert swot.mode == "standalone"
    assert swot.threats == []
