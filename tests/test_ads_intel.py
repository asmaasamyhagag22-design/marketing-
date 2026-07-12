# -*- coding: utf-8 -*-
"""ads_intel (roadmap Phase-2 #8, fixtures-first) — hermetic, no network.

Pins: strict schema; the deterministic ad-presence aggregation (longevity = the market's
own split-test verdict, computed in CODE); snapshot parsing (Graph API shape); empty is
VALID (a peer running no ads is itself a signal)."""
from __future__ import annotations

import json
from datetime import date

from ads_intel import CompetitorAd, ad_presence
from ads_intel.providers import FixtureAdsProvider, MetaAdLibraryProvider
from ads_intel.providers.meta_ad_library import ads_from_snapshot

_SNAPSHOT = {
    "source": "meta_ad_library", "brand_ref": "eldahan",
    "pulled_at": "2026-07-12T10:00:00+00:00",
    "ads": [
        {"id": "111", "page_name": "El Dahan", "ad_delivery_start_time": "2026-03-01",
         "publisher_platforms": ["FACEBOOK", "INSTAGRAM"],
         "ad_creative_bodies": ["أطعم مشويات في مصر — اطلب دلوقتي"],
         "ad_snapshot_url": "https://www.facebook.com/ads/library/?id=111",
         "media_type": "VIDEO"},
        {"id": "222", "page_name": "El Dahan", "ad_delivery_start_time": "2026-07-01",
         "publisher_platforms": ["INSTAGRAM"], "media_type": "IMAGE"},
        {"id": "333", "page_name": "El Dahan", "ad_delivery_start_time": "2026-01-05",
         "ad_delivery_stop_time": "2026-02-01", "media_type": "VIDEO"},   # stopped -> inactive
        {"id": None},                                                     # malformed -> skipped
    ],
}


def test_snapshot_parses_and_presence_aggregates():
    ads = ads_from_snapshot(_SNAPSHOT)
    assert len(ads) == 4                           # the id-less row parses with an empty ad_id
    active = [a for a in ads if a.is_active]
    assert {a.ad_id for a in active} >= {"111", "222"}
    assert not [a for a in ads if a.ad_id == "333" and a.is_active]

    p = ad_presence([a for a in ads if a.ad_id in ("111", "222", "333")],
                    today=date(2026, 7, 12))
    assert p.active_count == 2
    assert p.longest_days == (date(2026, 7, 12) - date(2026, 3, 1)).days   # 133
    assert p.proven_winners == 1                   # only the 133-day ad clears 60d
    assert p.formats == {"video": 1, "image": 1}   # the STOPPED video doesn't count
    assert p.platforms["instagram"] == 2


def test_presence_empty_is_honest_zeros():
    p = ad_presence([])
    assert p.active_count == 0 and p.longest_days == 0 and p.formats == {}


def test_providers_read_snapshot_and_fixture(tmp_path):
    (tmp_path / "eldahan.json").write_text(json.dumps(_SNAPSHOT, ensure_ascii=False),
                                           encoding="utf-8")
    prov = MetaAdLibraryProvider(str(tmp_path))
    ads = prov.fetch("eldahan")
    assert len(ads) >= 3 and ads[0].source == "meta_ad_library"
    # sanitized fixture rows round-trip through the fixture provider
    rows = [a.model_dump(mode="json") for a in ads]
    (tmp_path / "clean.json").write_text(json.dumps(rows, ensure_ascii=False),
                                         encoding="utf-8")
    assert len(FixtureAdsProvider(str(tmp_path)).fetch("clean")) == len(rows)
    assert prov.fetch("nobody") == []              # empty is VALID
