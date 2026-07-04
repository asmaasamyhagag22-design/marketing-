"""Adaptive discovery router: business-type -> engine, always empty-safe.

Routing only (no live Places): the Places engine is monkeypatched so we assert
WHICH engine fires per business type, and that the router never raises / never
returns None / never fabricates peers.
"""
from __future__ import annotations

from types import SimpleNamespace as NS

import competitor.router as router
from competitor.router import route_discovery, NullWebDiscoveryEngine
from competitor.models import PeerMatchResult, CompetitorProfile


def _profile(category=None, locations=None, offerings=None):
    cat = NS(value=category) if category is not None else None
    return NS(category=cat, locations=locations or [], offerings=offerings or [])


def _fake_peer(name="Peer", website="https://peer.com", place_id="p1"):
    cand = NS(name=name, website=website, place_id=place_id)
    return CompetitorProfile(candidate=cand, selection=NS(), reviews=[])


def _patch_places(monkeypatch, sentinel):
    calls = {"n": 0}
    def fake(profile, client, **kw):
        calls["n"] += 1
        return sentinel
    monkeypatch.setattr(router, "discover_competitors", fake)
    return calls


def test_unknown_never_touches_places_and_null_web_stays_standalone(monkeypatch):
    calls = _patch_places(monkeypatch, PeerMatchResult([_fake_peer()], False, 1, 1))
    res = route_discovery(_profile(category="other"))
    assert calls["n"] == 0                       # Places not called
    assert res.competitors == []                 # Null web engine -> nothing fabricated
    assert any("standalone" in n for n in res.notes)


def test_unknown_routes_to_web_engine(monkeypatch):
    # A B2B services company (no address, no cart) classifies UNKNOWN — it must
    # still get grounded SERP peers when a web engine is wired (was: hard skip ->
    # its SWOT could never have Opportunities/Threats).
    calls = _patch_places(monkeypatch, PeerMatchResult([_fake_peer()], False, 1, 1))
    class FakeWeb:
        name = "fake-web"
        def discover(self, profile, manifest=None):
            return [_fake_peer(place_id="w1"), _fake_peer(place_id="w1")]  # dup
    res = route_discovery(_profile(category="other"), web_engine=FakeWeb())
    assert calls["n"] == 0                       # still never Places
    assert len(res.competitors) == 1             # real web peer, deduped
    assert any("web engine" in n for n in res.notes)


def test_local_uses_places(monkeypatch):
    sentinel = PeerMatchResult([_fake_peer()], False, 5, 3, notes=["places ran"])
    calls = _patch_places(monkeypatch, sentinel)
    loc = NS(address_text="Road 9, Maadi", latitude=None, longitude=None)
    res = route_discovery(_profile(category="clinic", locations=[loc]), places_client=object())
    assert calls["n"] == 1
    assert len(res.competitors) == 1


def test_ecommerce_does_not_touch_places(monkeypatch):
    calls = _patch_places(monkeypatch, PeerMatchResult([_fake_peer()], False, 9, 9))
    res = route_discovery(_profile(category="ecommerce"), places_client=object())
    assert calls["n"] == 0                       # ecommerce NEVER depends on Places
    assert res.competitors == []                 # null web engine -> no peers
    assert any("web engine" in n for n in res.notes)


def test_ecommerce_uses_injected_web_engine(monkeypatch):
    _patch_places(monkeypatch, PeerMatchResult([], True, 0, 0))
    class FakeWeb:
        name = "fake-web"
        def discover(self, profile, manifest=None):
            return [_fake_peer(place_id="w1"), _fake_peer(place_id="w1")]  # dup
    res = route_discovery(_profile(category="ecommerce"), web_engine=FakeWeb())
    assert len(res.competitors) == 1             # deduped by place_id


def test_hybrid_merges_places_and_web(monkeypatch):
    _patch_places(monkeypatch, PeerMatchResult([_fake_peer(place_id="p1")], False, 4, 2))
    class FakeWeb:
        name = "fake-web"
        def discover(self, profile, manifest=None):
            return [_fake_peer(place_id="w2", website="https://other.com")]
    loc = NS(address_text="Mall", latitude=29.9, longitude=31.0)
    off = [NS(price_text="EGP 1", page_url="https://x.com/cart")]
    res = route_discovery(_profile(category="retail", locations=[loc], offerings=off),
                          places_client=object(), web_engine=FakeWeb())
    assert len(res.competitors) == 2             # p1 + w2
    assert any("HYBRID merge" in n for n in res.notes)


def test_engine_failure_degrades_safely(monkeypatch):
    def boom(profile, client, **kw):
        raise RuntimeError("places exploded")
    monkeypatch.setattr(router, "discover_competitors", boom)
    loc = NS(address_text="x", latitude=None, longitude=None)
    res = route_discovery(_profile(category="clinic", locations=[loc]), places_client=object())
    assert isinstance(res, PeerMatchResult)
    assert res.competitors == []
    assert any("failed safely" in n for n in res.notes)
