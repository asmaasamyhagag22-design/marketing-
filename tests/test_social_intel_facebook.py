# -*- coding: utf-8 -*-
"""Apify Facebook provider (Tier-2 wrap of the team's collector) — hermetic, no network.

Governance under test: authors hashed AT INGESTION and at fixture-conversion (PD-6); raw
names / profile URLs / actor `raw` payloads never survive; empty result is VALID; the
$20/month spend guard refuses before the cap, never after it.
"""
from __future__ import annotations

import json
from pathlib import Path

from social_intel.providers.apify_facebook import (
    ApifyFacebookProvider, brand_ref_of, signals_from_snapshot,
)
from social_intel.spend_guard import check_budget, est_cost_usd, record_pull

_SNAPSHOT = {
    "source": {"platform": "facebook", "input_url": "https://www.facebook.com/demopage/",
               "collected_at": "2026-07-11T15:00:43+00:00"},
    "profile": {"found": True, "name": "Demo Page", "username": None},
    "posts": [{
        "url": "https://www.facebook.com/demopage/posts/1",
        "text": "عرض اليوم على البرجر",
        "created_at": "2026-07-10T16:00:53.000Z",
        "reactions_count": 7,
        "raw": {"secret": "actor payload must be dropped"},
        "comments": [
            {"post_url": "https://www.facebook.com/demopage/posts/1",
             "text": "الأكل ممتاز بس التوصيل اتأخر",
             "created_at": "2026-07-11T04:00:20.000Z", "likes_count": 2,
             "author": {"id": "123", "name": "Mona Example",
                        "url": "https://www.facebook.com/profile.php?id=123",
                        "picture": "https://scontent.example/mona.jpg"},
             "raw": {"profileName": "Mona Example"}},
            {"post_url": "https://www.facebook.com/demopage/posts/1",
             "text": "", "author": {"name": "Empty Commenter"}},   # empty text -> skipped
        ],
    }],
}


def test_snapshot_ingestion_hashes_authors_and_drops_pii():
    signals = signals_from_snapshot(_SNAPSHOT)
    assert brand_ref_of(_SNAPSHOT) == "demopage"
    assert [s.signal_kind for s in signals] == ["post", "comment"]   # empty comment skipped
    post, comment = signals
    assert post.is_own_brand and post.lang == "ar" and post.like_count == 7
    assert comment.author_hash != "Mona Example" and len(comment.author_hash) >= 8
    dump = json.dumps([s.model_dump(mode="json") for s in signals], ensure_ascii=False)
    for pii in ("Mona Example", "profile.php", "scontent.example", "actor payload"):
        assert pii not in dump   # raw name / profile URL / avatar / actor raw: all dropped


def test_provider_reads_raw_snapshot_and_sanitized_fixture(tmp_path):
    # raw team snapshot on disk (local-only shape) -> hashed at ingestion
    (tmp_path / "demopage.json").write_text(
        json.dumps(_SNAPSHOT, ensure_ascii=False), encoding="utf-8")
    p = ApifyFacebookProvider(str(tmp_path))
    raw_loaded = p.fetch("demopage")
    assert len(raw_loaded) == 2 and raw_loaded[1].author_hash != "Mona Example"
    # sanitized fixture shape (what convert_facebook_snapshot commits) round-trips
    (tmp_path / "clean.json").write_text(
        json.dumps([s.model_dump(mode="json") for s in raw_loaded]), encoding="utf-8")
    assert len(p.fetch("clean")) == 2
    assert p.fetch("nope") == []   # empty is VALID (advisor flag)


def test_real_fiveguys_fixture_is_sanitized():
    fx = Path(__file__).resolve().parent.parent / "social_intel" / "fixtures" / "fiveguys.json"
    text = fx.read_text(encoding="utf-8")
    assert "profile.php" not in text and "profileUrl" not in text and '"raw"' not in text
    signals = ApifyFacebookProvider(str(fx.parent)).fetch("fiveguys")
    assert len(signals) >= 10
    assert all(len(s.author_hash) >= 8 and s.source == "facebook_apify" for s in signals)


def test_spend_guard_refuses_over_the_monthly_cap(tmp_path):
    from datetime import datetime, timezone
    ledger = tmp_path / "spend.jsonl"
    when = datetime(2026, 7, 12, tzinfo=timezone.utc)
    assert est_cost_usd(2000, cost_per_1k=5.0) == 10.0
    ok, msg = check_budget(2000, ledger=ledger, cap=20.0, cost_per_1k=5.0, month="2026-07")
    assert ok, msg
    record_pull(2000, url="https://www.facebook.com/x/", ledger=ledger,
                cost_per_1k=5.0, when=when)
    # $10 spent; another $15 would cross the owner's $20 cap -> REFUSED
    ok, msg = check_budget(3000, ledger=ledger, cap=20.0, cost_per_1k=5.0, month="2026-07")
    assert not ok and "REFUSED" in msg
    # a small pull still fits
    ok, _ = check_budget(1000, ledger=ledger, cap=20.0, cost_per_1k=5.0, month="2026-07")
    assert ok
