"""Hermetic tests for the brand-ad-driven reel generation (pure parts). The live STYLE + motion
render is verified out-of-CI."""
from reel.generate import _scene_prompts, _dna_refs


class _Brief:
    business_name = "WE"
    offerings = ["Fiber Internet", "eSIM"]
    palette_hex = ["#512283"]


def test_scene_prompts_are_brand_grounded():
    ps = _scene_prompts(_Brief(), 4)
    assert len(ps) >= 4
    assert any("Fiber Internet" in p for p in ps) and any("eSIM" in p for p in ps)  # real offerings
    assert all("WE" in p for p in ps)                                                # the brand
    assert all("text" not in p.lower() for p in ps)                                  # footage-only briefs


class _DNA:
    references_seen = ["https://ads/1.png", "https://ads/2.png"]


def test_dna_refs_prefers_supplied_dna():
    assert _dna_refs({}, None, _DNA()) == ["https://ads/1.png", "https://ads/2.png"]


def test_dna_refs_builds_when_none_supplied(monkeypatch):
    import brand.creative_dna as cd

    class _Stub:
        references_seen = ["https://ads/x.png"]
    monkeypatch.setattr(cd, "build_creative_dna", lambda profile, **k: _Stub())
    assert _dna_refs({"name": {"value": "WE"}}, None, None) == ["https://ads/x.png"]


def test_dna_refs_empty_when_no_dna_and_build_fails(monkeypatch):
    import brand.creative_dna as cd
    def _boom(*a, **k):
        raise RuntimeError("no search")
    monkeypatch.setattr(cd, "build_creative_dna", _boom)
    assert _dna_refs({}, None, None) == []
