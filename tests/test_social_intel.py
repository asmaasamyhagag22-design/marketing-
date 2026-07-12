"""U9 skeleton (fixtures-only, owner governance 2026-07-11) — hermetic."""
from __future__ import annotations

from social_intel import FixtureSocialProvider, SocialSignal


def test_fixture_signals_hashed_and_typed():
    out = FixtureSocialProvider().fetch("demo_brand")
    assert len(out) == 2 and all(isinstance(s, SocialSignal) for s in out)
    blob = " ".join(s.model_dump_json() for s in out)
    assert "Omar" not in blob and "Laila" not in blob        # PD-6: raw names never leave
    assert any(s.is_own_brand for s in out) and any(not s.is_own_brand for s in out)


def test_unknown_brand_valid_empty():
    assert FixtureSocialProvider().fetch("nobody") == []
