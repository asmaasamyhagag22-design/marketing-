# -*- coding: utf-8 -*-
"""T-TIER — tier mismatch outranks category match (owner: "a local single-branch burger
joint must NOT surface McDonald's"). Hermetic; exercises the decisive cap in _aggregate."""
from __future__ import annotations

from competitor.peer_match import PEER_FIT_FLOOR, _aggregate


def test_severe_size_mismatch_caps_below_the_peer_floor():
    # a perfect-category, same-language rival that is 100x the size -> NOT a real competitor
    bd = _aggregate({"sub_vertical": 1.0, "language": 1.0, "proximity": 0.8,
                     "size_similarity": 0.10, "audience_tier": None})
    assert bd.total < PEER_FIT_FLOOR            # decisive: capped, category can't carry it in


def test_opposite_price_tier_caps_below_the_floor():
    # perfect category but the opposite price band (budget joint vs premium chain)
    bd = _aggregate({"sub_vertical": 1.0, "language": 1.0, "proximity": 0.9,
                     "size_similarity": 0.7, "audience_tier": 0.0})
    assert bd.total < PEER_FIT_FLOOR


def test_genuine_near_tier_peer_is_untouched():
    # a same-category, similar-size, same-price rival scores high and is NOT capped
    bd = _aggregate({"sub_vertical": 0.8, "language": 1.0, "proximity": 0.8,
                     "size_similarity": 0.7, "audience_tier": 1.0})
    assert bd.total > PEER_FIT_FLOOR
    # exact weighted sum preserved (no cap fired)
    assert bd.total == round(
        sum(bd.weights_used[k] * v for k, v in
            {"sub_vertical": 0.8, "language": 1.0, "proximity": 0.8,
             "size_similarity": 0.7, "audience_tier": 1.0}.items()), 4)


def test_cap_needs_the_signal_present_not_guessed():
    # size/tier unavailable (None) -> no cap; the web-search / no-Places path is unaffected
    bd = _aggregate({"sub_vertical": 1.0, "language": 1.0,
                     "size_similarity": None, "audience_tier": None})
    assert bd.total > PEER_FIT_FLOOR            # nothing to penalize -> unchanged
