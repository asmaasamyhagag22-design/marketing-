# -*- coding: utf-8 -*-
"""Competitor Registry (owner-caught non-determinism) — hermetic.

First discovery establishes a persisted baseline; later runs DIFF against it
(present/disappeared/new-pending) and NEVER silently replace. SWOT computes against the
approved set. Identity changes are the owner's (this module never auto-approves)."""
from __future__ import annotations

from competitor.registry import (
    approved_competitors, competitor_key, diff_competitors, establish_or_diff, load_registry,
)


def _c(name, site):
    return {"selection": {"name": name, "website": site}, "candidate": {"name": name}}


def test_key_is_stable_by_domain():
    assert competitor_key("Foo", "https://www.foo-clinic.com/x?y=1") == "foo-clinic.com"
    assert competitor_key("Foo", "http://foo-clinic.com") == "foo-clinic.com"   # same rival
    assert competitor_key("مطعم الدهان", "") == "مطعمالدهان"                     # name fallback


def test_first_run_establishes_baseline(tmp_path):
    disc = [_c("A", "https://a.com"), _c("B", "https://b.com")]
    out = establish_or_diff("nti", disc, store_dir=str(tmp_path), now="2026-07-12")
    assert out["established"] is True
    assert sorted(out["approved_keys"]) == ["a.com", "b.com"]
    reg = load_registry("nti", store_dir=str(tmp_path))
    assert {e["key"] for e in reg["entries"]} == {"a.com", "b.com"}
    assert all(e["status"] == "approved" for e in reg["entries"])


def test_later_run_diffs_without_silent_replacement(tmp_path):
    establish_or_diff("nti", [_c("A", "https://a.com"), _c("B", "https://b.com")],
                      store_dir=str(tmp_path), now="d1")
    # next run: A stays, B gone, C is new
    out = establish_or_diff("nti", [_c("A", "https://a.com"), _c("C", "https://c.com")],
                            store_dir=str(tmp_path), now="d2")
    assert out["established"] is False
    d = out["diff"]
    assert [e["key"] for e in d["still_present"]] == ["a.com"]
    assert [e["key"] for e in d["disappeared"]] == ["b.com"]     # flagged, not deleted
    assert [e["key"] for e in d["new_pending"]] == ["c.com"]     # pending, NOT auto-added
    # the persisted baseline is UNCHANGED (no silent replacement)
    reg = load_registry("nti", store_dir=str(tmp_path))
    assert {e["key"] for e in reg["entries"]} == {"a.com", "b.com"}
    # SWOT computes only against the approved baseline (a.com, b.com) — C is excluded
    approved = approved_competitors([_c("A", "https://a.com"), _c("C", "https://c.com")],
                                    out["approved_keys"])
    assert [_c_key(c) for c in approved] == ["a.com"]            # only the still-present approved


def _c_key(c):
    from competitor.registry import _entry_of
    return _entry_of(c)["key"]


def test_removed_entry_drops_from_approved(tmp_path):
    establish_or_diff("x", [_c("A", "https://a.com")], store_dir=str(tmp_path), now="d1")
    reg = load_registry("x", store_dir=str(tmp_path))
    reg["entries"][0]["status"] = "removed"                     # owner removed it (HITL)
    from competitor.registry import save_registry
    save_registry(reg, store_dir=str(tmp_path))
    out = establish_or_diff("x", [_c("A", "https://a.com")], store_dir=str(tmp_path), now="d2")
    assert out["approved_keys"] == []                           # a removed rival is not approved
    assert out["diff"]["still_present"] == []                   # and not counted present


def test_diff_is_pure_no_mutation():
    reg = {"brand_ref": "x", "entries": [{"key": "a.com", "name": "A", "status": "approved"}]}
    diff_competitors(reg, [_c("B", "https://b.com")])
    assert reg["entries"] == [{"key": "a.com", "name": "A", "status": "approved"}]
