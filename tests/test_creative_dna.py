"""BrandCreativeDNA — STRICT brand-ownership filter (the grounded-image principle).

Hermetic: the harvester (Serper image search) and the image fetcher are injected; the
multimodal caller is a MockCaller. No network, no vision API. The filter mirrors the copy
gate — only the brand's OWN creatives count; doubtful search hits are rejected; if nothing
brand-owned passes, the DNA falls back to the brand's scraped site images, else a stub.
"""
from __future__ import annotations

from brand.creative_dna import (
    BrandCreativeDNA, _DnaResponse, _is_brand_owned, build_creative_dna, harvest_creative_urls,
)
from business_profile.llm.caller import MockCaller

# A real brand: its own site + a known Facebook profile (handle 'WeBrand').
_PROFILE = {
    "name": {"value": "WE"},
    "source_url": "https://we.com.eg/",
    "social_presence": [{"platform": "facebook", "url": "https://www.facebook.com/WeBrand"}],
    "visual": {"content_images": ["https://cdn.we.com.eg/site-photo.jpg"]},
}


def _dna_resp() -> _DnaResponse:
    return _DnaResponse(
        layout_philosophy="full-bleed lifestyle photo with a rounded purple block on the left",
        composition_patterns="subject right, generous left negative space",
        typographic_character="bold condensed uppercase headline, big scale jump",
        color_usage="purple dominates as a solid field; white text; sparing accent",
        imagery_style="warm candid Egyptian lifestyle photography",
        mood="optimistic, human, premium", motifs="the rounded purple 'we' block",
        text_density="minimal — one headline + CTA",
        signature_moves="purple block bleeding off-edge with white knockout type",
        do_list=["lead with the purple block"], dont_list=["no clutter"],
    )


def _cand(image_url, page_host="", page_link="", title=""):
    return {"image_url": image_url, "page_host": page_host, "page_link": page_link, "title": title}


# ---- harvest ----

def test_harvest_no_key_returns_empty(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    assert harvest_creative_urls("WE") == []


def test_harvest_returns_candidates_with_page_info(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    import scraper.net as net
    monkeypatch.setattr(net, "post_json", lambda url, body, **kw: {"images": [
        {"imageUrl": "https://img.cdn/x.jpg", "link": "https://we.com.eg/campaign", "domain": "we.com.eg"},
    ]})
    cands = harvest_creative_urls("WE", brand_domain="we.com.eg", num=5)
    assert cands and cands[0]["image_url"] == "https://img.cdn/x.jpg"
    assert cands[0]["page_host"] == "we.com.eg" and "campaign" in cands[0]["page_link"]


# ---- the brand-ownership predicate ----

def test_is_brand_owned_only_brand_site_or_confirmed_social():
    social = [("www.facebook.com", "/webrand")]
    # brand's own site (any subdomain) -> owned
    assert _is_brand_owned(_cand("i", "shop.we.com.eg", "https://shop.we.com.eg/a"), "https://we.com.eg/", social)
    # the brand's OWN facebook page (handle in link) -> owned
    assert _is_brand_owned(_cand("i", "facebook.com", "https://facebook.com/WeBrand/photos/9"), "https://we.com.eg/", social)
    # facebook, but a DIFFERENT page (handle absent) -> NOT owned
    assert not _is_brand_owned(_cand("i", "facebook.com", "https://facebook.com/SomeoneElse/x"), "https://we.com.eg/", social)
    # a random news/aggregator/stock domain -> NOT owned
    assert not _is_brand_owned(_cand("i", "adsoftheworld.com", "https://adsoftheworld.com/x"), "https://we.com.eg/", social)
    assert not _is_brand_owned(_cand("i", "shutterstock.com", "https://shutterstock.com/x"), "https://we.com.eg/", social)


# ---- build: tiering, counts, fallback ----

def test_brand_owned_kept_others_rejected_counts_recorded():
    harvested = [
        _cand("https://img/brand.jpg", "we.com.eg", "https://we.com.eg/ad"),          # OWNED
        _cand("https://img/fb.jpg", "facebook.com", "https://facebook.com/WeBrand/p"), # OWNED (social)
        _cand("https://img/news.jpg", "adsoftheworld.com", "https://adsoftheworld.com/x"),  # rejected
        _cand("https://img/stock.jpg", "shutterstock.com", "https://shutterstock.com/x"),   # rejected
    ]
    captured = {}
    def fetch(urls):
        captured["urls"] = list(urls)
        return [(u, b"x", "image/jpeg") for u in urls]
    dna = build_creative_dna(_PROFILE, caller=MockCaller({"creative_dna": _dna_resp()}),
                             _harvester=lambda *a, **k: harvested, _image_fetcher=fetch)
    assert dna.harvested_total == 4 and dna.kept_after_brand_filter == 2
    # the two brand-owned ADS come FIRST, then the scraped site image; rejects never appear.
    assert captured["urls"][:2] == ["https://img/brand.jpg", "https://img/fb.jpg"]
    assert "https://cdn.we.com.eg/site-photo.jpg" in captured["urls"]
    assert all(bad not in captured["urls"] for bad in ("https://img/news.jpg", "https://img/stock.jpg"))
    assert dna.site_images_used == 1 and dna.used_vision is True


def test_no_brand_owned_falls_back_to_site_images():
    harvested = [_cand("https://img/news.jpg", "adsoftheworld.com", "https://adsoftheworld.com/x")]
    dna = build_creative_dna(_PROFILE, caller=MockCaller({"creative_dna": _dna_resp()}),
                             _harvester=lambda *a, **k: harvested,
                             _image_fetcher=lambda urls: [(u, b"x", "image/jpeg") for u in urls])
    assert dna.kept_after_brand_filter == 0          # nothing brand-owned from search
    assert dna.site_images_used == 1                  # but the scraped site image carries it
    assert dna.used_vision is True


def test_no_brand_images_at_all_is_honest_stub():
    profile = {"name": {"value": "WE"}, "source_url": "https://we.com.eg/", "visual": {}}
    harvested = [_cand("https://img/news.jpg", "adsoftheworld.com", "https://adsoftheworld.com/x")]
    dna = build_creative_dna(profile, caller=MockCaller({"creative_dna": _dna_resp()}),
                             _harvester=lambda *a, **k: harvested, _image_fetcher=lambda urls: [])
    assert dna.used_vision is False and dna.kept_after_brand_filter == 0
    assert "honest UNKNOWN" in (dna.note or "")


def test_build_no_caller_returns_stub():
    dna = build_creative_dna(_PROFILE, caller=None,
                             _harvester=lambda *a, **k: [], _image_fetcher=lambda urls: [])
    assert isinstance(dna, BrandCreativeDNA)
    assert dna.used_vision is False and dna.business_name == "WE"


# ---- tier 2: the brand's REAL ads on a reputable creative portfolio (attribution-guarded) ----

def test_brand_tokens_skips_short_words():
    from brand.creative_dna import _brand_tokens
    assert _brand_tokens("Telecom Egypt", "te.eg") == ["telecom", "egypt"]   # 'te' too short
    assert _brand_tokens("WE", "we.com.eg") == []                            # all short -> no attribution


def test_tier2_reputable_portfolio_only_when_brand_named():
    social = []
    toks = ["telecom", "egypt"]                                              # from "Telecom Egypt"
    # a real ad on adsoftheworld with the brand NAMED in the link -> accepted (tier 2)
    assert _is_brand_owned(_cand("i", "adsoftheworld.com",
                                 "https://adsoftheworld.com/campaigns/telecom-egypt-we"),
                           "https://te.eg/", social, toks)
    # attribution via the TITLE also counts
    assert _is_brand_owned(_cand("i", "www.behance.net", "https://behance.net/gallery/123",
                                 "Telecom Egypt — WE rebrand"), "https://te.eg/", social, toks)
    # SAME reputable host but a DIFFERENT brand named -> rejected (wrong-brand guard)
    assert not _is_brand_owned(_cand("i", "adsoftheworld.com",
                                     "https://adsoftheworld.com/campaigns/vodafone-x", "Vodafone ad"),
                               "https://te.eg/", social, toks)
    # stock host -> rejected even if the brand is named
    assert not _is_brand_owned(_cand("i", "shutterstock.com", "https://shutterstock.com/telecom-egypt"),
                               "https://te.eg/", social, toks)
    # no usable tokens (short brand) -> tier 2 can't attribute -> rejected (old strict behavior)
    assert not _is_brand_owned(_cand("i", "behance.net", "https://behance.net/x"),
                               "https://te.eg/", social, [])
