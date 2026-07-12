# -*- coding: utf-8 -*-
"""Google Maps review provider (parse-only, PD-4/PD-6) — hermetic, no network.

Mirrors the Facebook-wrap governance: authors hashed at ingestion, raw names never
survive serialization, relative dates -> honest None, empty result is VALID."""
from __future__ import annotations

import json

from reviews.providers.google_maps import GoogleMapsReviewProvider, reviews_from_snapshot

_SNAPSHOT = {
    "source": "google_maps",
    "brand_ref": "demo_clinic_maps",
    "is_own_brand": True,
    "place_id": "ChIJdemo123",
    "pulled_at": "2026-07-12T10:00:00+00:00",
    "reviews": [
        {"rating": 5, "text": "الدكتور ممتاز والمكان نضيف", "author": "Mona Example",
         "relative_time": "a month ago", "language_code": "ar"},
        {"rating": 2, "text": "Waited two hours past my appointment", "author": "John Doe",
         "relative_time": "3 weeks ago", "language_code": "en"},
        {"rating": 4, "text": "", "author": "Empty Reviewer"},          # empty text -> skipped
    ],
}


def test_snapshot_ingestion_hashes_authors_and_stays_honest():
    reviews = reviews_from_snapshot(_SNAPSHOT)
    assert len(reviews) == 2                      # the empty-text row skipped
    ar, en = reviews
    assert ar.source == "google_maps" and ar.lang == "ar" and en.lang == "en"
    assert ar.author_hash != "Mona Example" and len(ar.author_hash) >= 8
    assert ar.review_date is None                 # relative time -> never a fabricated date
    assert "place_id:ChIJdemo123" in ar.source_url
    dump = json.dumps([r.model_dump(mode="json") for r in reviews], ensure_ascii=False)
    assert "Mona Example" not in dump and "John Doe" not in dump


def test_provider_reads_raw_snapshot_and_sanitized_fixture(tmp_path):
    (tmp_path / "demo_clinic_maps.json").write_text(
        json.dumps(_SNAPSHOT, ensure_ascii=False), encoding="utf-8")
    p = GoogleMapsReviewProvider(str(tmp_path))
    raw_loaded = p.fetch("demo_clinic_maps")
    assert len(raw_loaded) == 2
    # sanitized fixture shape (what convert_reviews_snapshot commits) round-trips
    (tmp_path / "clean.json").write_text(
        json.dumps([r.model_dump(mode="json") for r in raw_loaded]), encoding="utf-8")
    assert len(p.fetch("clean")) == 2
    assert p.fetch("nope") == []                  # empty is VALID (advisor flag)


def test_reviews_feed_absa_rows_directly():
    # ABSA accepts provider-agnostic rows; a pulled batch is tagged own/peer by its snapshot.
    from reviews.absa import _row_fields
    reviews = reviews_from_snapshot(_SNAPSHOT)
    rows = [{"id": f"G{i+1}", "text": r.text, "is_own_brand": _SNAPSHOT["is_own_brand"]}
            for i, r in enumerate(reviews)]
    rid, text, own = _row_fields(rows[0], 0)
    assert rid == "G1" and own is True and "الدكتور" in text
