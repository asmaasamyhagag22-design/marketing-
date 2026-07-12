# -*- coding: utf-8 -*-
"""IG Business Discovery provider (U9 Tier-1 — the official door; the scraper was
rejected) — hermetic. Pins: own-mode captions+comments with authors hashed at ingestion
(usernames never survive), peer-mode captions flagged is_own_brand=False, provider reads
raw snapshots AND sanitized fixtures, empty is VALID."""
from __future__ import annotations

import json

from social_intel.providers.ig_business import IgBusinessProvider, signals_from_snapshot

_OWN = {
    "source": "ig_business", "mode": "own", "brand_ref": "myclinic", "is_own_brand": True,
    "ig_user_id": "17840000000000000", "pulled_at": "2026-07-12T12:00:00+00:00",
    "media": [{
        "id": "m1", "caption": "خصم الصيف على جلسات الليزر",
        "permalink": "https://www.instagram.com/p/AAA/",
        "timestamp": "2026-07-10T09:00:00+0000", "like_count": 40,
        "comments": [
            {"id": "c1", "text": "استنيت ساعتين في العيادة", "username": "mona.example",
             "timestamp": "2026-07-10T10:00:00+0000", "like_count": 2},
            {"id": "c2", "text": "", "username": "empty.user"},
        ],
    }],
}
_PEER = {
    "source": "ig_business", "mode": "peer", "brand_ref": "peerclinic",
    "is_own_brand": False, "peer_username": "peer.clinic",
    "pulled_at": "2026-07-12T12:00:00+00:00",
    "media": [{"caption": "احجز كشفك دلوقتي", "permalink": "https://www.instagram.com/p/BBB/",
               "timestamp": "2026-07-09T09:00:00+0000", "like_count": 10}],
}


def test_own_mode_hashes_comment_authors_and_keeps_the_arc():
    sig = signals_from_snapshot(_OWN)
    kinds = [s.signal_kind for s in sig]
    assert kinds == ["caption", "comment"]              # empty comment skipped
    cap, com = sig
    assert cap.is_own_brand and com.is_own_brand
    assert com.lang == "ar" and "استنيت" in com.text
    assert com.author_hash != "mona.example" and len(com.author_hash) >= 8
    dump = json.dumps([s.model_dump(mode="json") for s in sig], ensure_ascii=False)
    assert "mona.example" not in dump and "empty.user" not in dump   # PII never survives


def test_peer_mode_is_marketing_voice_not_own():
    sig = signals_from_snapshot(_PEER)
    assert len(sig) == 1 and sig[0].signal_kind == "caption"
    assert sig[0].is_own_brand is False                 # routes O/T side, never S/W
    assert sig[0].source == "ig_business_discovery"


def test_provider_reads_raw_and_sanitized(tmp_path):
    (tmp_path / "myclinic_ig.json").write_text(json.dumps(_OWN, ensure_ascii=False),
                                               encoding="utf-8")
    p = IgBusinessProvider(str(tmp_path))
    loaded = p.fetch("myclinic")
    assert len(loaded) == 2
    rows = [s.model_dump(mode="json") for s in loaded]
    (tmp_path / "clean.json").write_text(json.dumps(rows, ensure_ascii=False),
                                         encoding="utf-8")
    assert len(p.fetch("clean")) == 2
    assert p.fetch("nobody") == []                      # empty is VALID
