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


def test_labeling_kit_is_startable_the_moment_data_exists(tmp_path):
    # U8c: 100-review label-ready JSONL (aspect sheet embedded, empty label slots,
    # evidence_quote contract documented) + the one-page guide. Zero network.
    from reviews import FixtureReviewProvider
    from reviews.labeling_kit import build_labeling_file, write_guide
    from reviews.taxonomy import aspects_for
    revs = FixtureReviewProvider().fetch("demo_clinic")
    out = build_labeling_file(revs, "clinic", tmp_path / "label_me.jsonl")
    lines = [__import__("json").loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    header, rows = lines[0], lines[1:]
    assert any(a["aspect"] == "doctor_competence" for a in header["_aspect_sheet"])
    assert len(rows) == 3 and all(r["labels"] == [] and "text" in r for r in rows)
    guide = write_guide(tmp_path)
    assert "substring" in guide.read_text(encoding="utf-8")
    assert len(aspects_for(None)) >= 6                       # universal default exists
