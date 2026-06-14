"""Opus creative director (reel.creative_director).

The Opus vision call needs a key + network; these tests cover the deterministic
parts: identity-block assembly, JSON parsing, and honest-degrade. The "designs a
real creative reel" behaviour is shown by the live elkbabgi run.
"""
from __future__ import annotations

from reel.creative_director import _identity_block, _safe_json_object, design_creative_reel


def _profile():
    return {
        "name": {"value": "Qasr Elkbabgi"},
        "category": {"value": "restaurant"},
        "description": {"value": "An Egyptian grill."},
        "offerings": [{"name": "grilled dishes"}],
        "languages": ["ar", "en"],
    }


def test_identity_block_has_core_fields():
    b = _identity_block(_profile())
    assert "Qasr Elkbabgi" in b
    assert "grilled dishes" in b


def test_safe_json_object_strips_fences_and_handles_garbage():
    assert _safe_json_object('```json\n{"scenes":[]}\n```') == {"scenes": []}
    assert _safe_json_object("not json") is None


def test_no_key_degrades_to_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert design_creative_reel(_profile(), ["https://x.com/a.jpg"], api_key=None) is None


def test_no_photos_returns_none(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert design_creative_reel(_profile(), []) is None
