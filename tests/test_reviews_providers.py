"""U8a review layer — fixtures-first, hermetic. Pins: the privacy rule (author_hash never a
raw name), empty-is-valid, malformed rows skipped not fatal, strict schema."""
from __future__ import annotations

from reviews import FixtureReviewProvider, Review


def test_fixture_provider_loads_and_hashes_authors():
    p = FixtureReviewProvider()
    out = p.fetch("demo_clinic")
    assert len(out) == 3 and all(isinstance(r, Review) for r in out)
    blob = " ".join(r.model_dump_json() for r in out)
    assert "Mona" not in blob and "Ahmed" not in blob     # privacy: raw names never leave
    assert all(len(r.author_hash) >= 8 for r in out)
    ar = [r for r in out if r.lang == "ar"]
    assert len(ar) == 2 and any("الانتظار" in r.text for r in ar)


def test_unknown_brand_is_valid_empty_and_limit_respected():
    p = FixtureReviewProvider()
    assert p.fetch("nobody_here") == []                    # empty is VALID (advisor flag)
    assert len(p.fetch("demo_clinic", limit=1)) == 1


def test_malformed_rows_skip_not_fatal(tmp_path):
    (tmp_path / "b.json").write_text(
        '[{"author":"X","rating":9,"text":"bad rating"},{"author":"Y","text":"ok","rating":4}]',
        encoding="utf-8")
    out = FixtureReviewProvider(str(tmp_path)).fetch("b")
    assert len(out) == 1 and out[0].rating == 4            # the 9-star row rejected silently
