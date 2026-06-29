"""Hermetic tests for the RAG retriever (Pillar 2 / Step 2).

No network: embeddings are an INJECTED fake embed_fn (deterministic vectors), the
same provider-injection discipline as the embeddings / MockCaller tests. Covers:
cosine ranking, top-K retrieval, the per-group query map, graceful degrade when
embeddings are None, provenance preservation, and the cap-lift of
build_full_evidence_pack. The live text-embedding-004 path is out-of-CI.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

# Stub playwright (same defensive pattern as test_evidence_pack.py)
_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for _n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, _n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from scraper.schemas import (  # noqa: E402
    BoundingBox, LanguageEntry, PageRecord, PageTier, PageType,
    ReadinessReport, RobotsRecord, Section, ScrapeManifest, ScrapeMeta,
    SiteMetadata, TextBlock,
)
from business_profile.llm.evidence_pack import (  # noqa: E402
    DEFAULT_MAX_PER_PAGE_TYPE, EvidenceBlock, EvidencePack, build_evidence_pack,
)
from business_profile.llm.rag import (  # noqa: E402
    DEFAULT_K, RagRetriever, build_full_evidence_pack, build_rag_retriever,
    default_query_for,
)
from business_profile.build import build_profile  # noqa: E402
from business_profile.llm.caller import MockCaller  # noqa: E402
from business_profile.llm.extractor import run_llm_extraction  # noqa: E402
from business_profile.llm.responses import (  # noqa: E402
    IdentityResponse, OfferingItem, OfferingsResponse,
    PositioningResponse, TrustResponse,
)
from business_profile.schemas import (  # noqa: E402
    BusinessProfile, Confidence, ExtractionMeta, LLMEvidenceRef, ProfileQuality,
)


# ---------------------------------------------------------------------
# Manifest helpers (mirrors test_evidence_pack.py)
# ---------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _tb(bid: str, url: str, tag: str, text: str,
        section: Section = Section.MAIN, above_fold: bool = False) -> TextBlock:
    return TextBlock(
        block_id=bid, page_url=url, tag=tag, text=text, section=section,
        selector=f"{tag}#{bid}",
        bbox=BoundingBox(x=10, y=100, width=200, height=20),
        above_fold=above_fold,
    )


def _page(url: str, page_type: PageType, blocks: list[TextBlock]) -> PageRecord:
    return PageRecord(
        url=url, final_url=url, http_status=200, fetched_at=_now(),
        fetch_duration_ms=1000, page_type=page_type, tier=PageTier.HIGH,
        viewport_width=1366, viewport_height=800, text_blocks=blocks,
    )


def _manifest(pages: list[PageRecord]) -> ScrapeManifest:
    home = pages[0].final_url if pages else "https://x.com/"
    return ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url=home, normalized_url=home, final_url=home, scraped_at=_now(),
        ),
        robots=RobotsRecord(checked=True, allowed=True),
        readiness=ReadinessReport(
            has_homepage=True, has_internal_pages=True, has_contact_signals=False,
            has_visual_signals=False, has_cta_candidates=False, has_metadata=False,
            ready_for_extraction=True,
        ),
        languages=[LanguageEntry(code="en", proportion=1.0)],
        pages=pages,
        site_metadata=SiteMetadata(),
    )


def _empty_profile() -> BusinessProfile:
    return BusinessProfile(
        source_url="https://x.com/",
        extraction_meta=ExtractionMeta(manifest_path="x", extracted_at=_now()),
        quality=ProfileQuality(
            has_name=False, has_category=False, has_offerings=False,
            has_audience=False, has_value_propositions=False, has_tone=False,
            has_contact=False, has_visual=False,
            fields_extracted=0, fields_inferred=0, fields_missing=0,
            major_missing=["category", "offerings"], ready_for_strategy=False,
        ),
    )


# ---------------------------------------------------------------------
# Pack + fake-embedding helpers (no manifest needed)
# ---------------------------------------------------------------------

def _eb(bid: str, text: str, url: str = "https://x.com/p") -> EvidenceBlock:
    return EvidenceBlock(
        block_id=bid, page_url=url, page_type="homepage",
        section="main", tag="p", above_fold=False, text=text,
    )


def _pack(blocks: list[EvidenceBlock]) -> EvidencePack:
    return EvidencePack(
        source_url="https://x.com/", languages=["en"], blocks=blocks,
        blocks_total_in_manifest=99, blocks_after_filter=len(blocks),
        block_count=len(blocks), block_ids=[b.block_id for b in blocks],
        missing_fields=["category"],
    )


def _embed_from(mapping: dict[str, list[float]]):
    """A deterministic fake embed_fn: text -> vector via a fixed mapping."""
    def fn(texts):
        return [mapping[t] for t in texts]
    return fn


# Three blocks living in 3 orthogonal semantic directions
_B1 = _eb("home_p_0001", "Espresso, latte and cold brew on our menu")   # offerings axis
_B2 = _eb("home_p_0002", "ISO 9001 certified and trusted by Vodafone")  # trust axis
_B3 = _eb("home_p_0003", "We serve customers across Cairo and Giza")     # area axis
_MAP = {
    _B1.text: [1.0, 0.0, 0.0],
    _B2.text: [0.0, 1.0, 0.0],
    _B3.text: [0.0, 0.0, 1.0],
    "menu drinks": [1.0, 0.0, 0.0],          # query closest to B1
    "certifications": [0.0, 1.0, 0.0],       # query closest to B2
    "menu and a little trust": [0.9, 0.4, 0.0],  # query: B1 first, then B2
}


# ---------------------------------------------------------------------
# default_query_for
# ---------------------------------------------------------------------

def test_default_query_for_covers_all_four_groups():
    for group in ("identity", "offerings", "positioning", "trust"):
        q = default_query_for(group)
        assert isinstance(q, str) and len(q) > 0
    assert default_query_for("nonexistent_group") is None


# ---------------------------------------------------------------------
# retrieve: ranking + top-K
# ---------------------------------------------------------------------

def test_retrieve_returns_single_most_relevant_block():
    r = RagRetriever(_pack([_B1, _B2, _B3]), _pack([]), embed_fn=_embed_from(_MAP))
    out = r.retrieve("menu drinks", k=1)
    assert out.block_count == 1
    assert out.blocks[0].block_id == _B1.block_id


def test_retrieve_top_k_is_ordered_by_relevance():
    r = RagRetriever(_pack([_B1, _B2, _B3]), _pack([]), embed_fn=_embed_from(_MAP))
    out = r.retrieve("menu and a little trust", k=2)
    assert [b.block_id for b in out.blocks] == [_B1.block_id, _B2.block_id]


def test_retrieve_preserves_provenance():
    r = RagRetriever(_pack([_B1, _B2, _B3]), _pack([]), embed_fn=_embed_from(_MAP))
    out = r.retrieve("certifications", k=1)
    b = out.blocks[0]
    assert b.block_id == _B2.block_id
    assert b.page_url == _B2.page_url
    assert b.text == _B2.text                 # verbatim
    assert out.block_ids == [_B2.block_id]     # validator-facing list matches


def test_retrieve_embeds_blocks_once_and_caches():
    calls = {"n": 0}
    def counting_embed(texts):
        calls["n"] += 1
        return [_MAP[t] for t in texts]
    r = RagRetriever(_pack([_B1, _B2, _B3]), _pack([]), embed_fn=counting_embed)
    r.retrieve("menu drinks", k=1)
    r.retrieve("certifications", k=1)
    # 1 block-embedding call (cached) + 1 query-embedding call per retrieve == 3
    assert calls["n"] == 3


# ---------------------------------------------------------------------
# graceful degrade
# ---------------------------------------------------------------------

def test_retrieve_falls_back_when_embeddings_unavailable():
    fallback = _pack([_B3])
    r = RagRetriever(_pack([_B1, _B2, _B3]), fallback, embed_fn=lambda texts: None)
    out = r.retrieve("menu drinks", k=2)
    assert out is fallback                     # today's behavior, no regression


def test_retrieve_falls_back_on_empty_full_pack():
    fallback = _pack([_B1])
    r = RagRetriever(_pack([]), fallback, embed_fn=_embed_from(_MAP))
    assert r.retrieve("menu drinks", k=2) is fallback


def test_retrieve_falls_back_when_query_embedding_fails():
    # blocks embed fine, but the query embedding returns None
    state = {"first": True}
    def flaky(texts):
        if state["first"]:
            state["first"] = False
            return [_MAP[t] for t in texts]   # block batch ok
        return None                            # query batch fails
    fallback = _pack([_B2])
    r = RagRetriever(_pack([_B1, _B2, _B3]), fallback, embed_fn=flaky)
    assert r.retrieve("menu drinks", k=2) is fallback


# ---------------------------------------------------------------------
# build_full_evidence_pack: the selection cap is lifted
# ---------------------------------------------------------------------

def test_build_full_evidence_pack_lifts_the_per_page_type_cap():
    n = DEFAULT_MAX_PER_PAGE_TYPE + 10  # 70 distinct product blocks, one page type
    blocks = [
        _tb(f"prod_p_{i:04d}", "https://x.com/products", "p",
            f"Product number {i}: a distinct described item for sale.")
        for i in range(n)
    ]
    m = _manifest([_page("https://x.com/products", PageType.PRODUCTS, blocks)])
    prof = _empty_profile()

    capped = build_evidence_pack(m, prof)
    full = build_full_evidence_pack(m, prof)

    assert capped.block_count == DEFAULT_MAX_PER_PAGE_TYPE   # 60: the quota binds
    assert full.block_count == n                             # 70: every block kept


def test_build_rag_retriever_wires_full_and_fallback_packs():
    n = DEFAULT_MAX_PER_PAGE_TYPE + 10
    blocks = [
        _tb(f"prod_p_{i:04d}", "https://x.com/products", "p",
            f"Product number {i}: a distinct described item for sale.")
        for i in range(n)
    ]
    m = _manifest([_page("https://x.com/products", PageType.PRODUCTS, blocks)])
    r = build_rag_retriever(m, _empty_profile(), embed_fn=_embed_from(_MAP))
    assert r.full_pack.block_count == n
    assert r.fallback_pack.block_count == DEFAULT_MAX_PER_PAGE_TYPE
    assert DEFAULT_K == 200


# ---------------------------------------------------------------------
# Step 3 wiring: extractor + build_profile
# ---------------------------------------------------------------------

def _any_embed(texts):
    """A deterministic, never-None fake embed_fn for arbitrary text (so retrieval
    succeeds and returns top-K; ranking is irrelevant when K >= #blocks)."""
    return [[float(len(t)), float(len(t.split()))] for t in texts]


def _min_staged():
    return {
        "identity": IdentityResponse(),
        "offerings": OfferingsResponse(),
        "positioning": PositioningResponse(),
        "trust": TrustResponse(),
    }


def test_extractor_feeds_retrieved_blocks_to_each_group():
    """A block that lives in the FULL pack but not the global fallback pack must
    reach each group's prompt when a retriever is wired in — and must NOT when
    it isn't (today's behavior)."""
    special = _eb("prod_p_0099", "Exclusive Diamond Catering Package for weddings")
    full = _pack([_B1, _B2, _B3, special])
    glob = _pack([_B1, _B2, _B3])  # the special block is absent here
    retr = RagRetriever(full, glob, embed_fn=_any_embed)

    mock = MockCaller(_min_staged())
    run_llm_extraction(glob, mock, retriever=retr)
    off = next(c for c in mock.calls if c.group_name == "offerings")
    assert "prod_p_0099" in off.user_prompt          # RAG surfaced the beyond-cap block

    mock2 = MockCaller(_min_staged())
    run_llm_extraction(glob, mock2)                  # no retriever
    off2 = next(c for c in mock2.calls if c.group_name == "offerings")
    assert "prod_p_0099" not in off2.user_prompt     # global pack lacks it


def _catalog_manifest():
    """Homepage + a 70-product page. The global pack caps that page type at 60,
    so prod_p_0069 (inserted last, equal score) is DROPPED from the global pack
    but kept in the full pack — a real offering the count cap would silently lose."""
    n = DEFAULT_MAX_PER_PAGE_TYPE + 10  # 70
    products = [
        _tb(f"prod_p_{i:04d}", "https://shop.com/products", "p",
            f"Product number {i}: a distinct described item for sale.")
        for i in range(n - 1)
    ]
    products.append(_tb(
        "prod_p_0069", "https://shop.com/products", "p",
        "Exclusive Diamond Catering Package for weddings and corporate events",
    ))
    home = [_tb("home_h1_0001", "https://shop.com/", "h1",
                "Fine dining and catering in Cairo", above_fold=True)]
    return _manifest([
        _page("https://shop.com/", PageType.HOMEPAGE, home),
        _page("https://shop.com/products", PageType.PRODUCTS, products),
    ])


def _staged_offering_citing_beyond_cap():
    staged = _min_staged()
    staged["offerings"] = OfferingsResponse(
        offerings=[OfferingItem(
            name="Diamond Catering Package",
            short_description="Catering for weddings and corporate events.",
            evidence=[LLMEvidenceRef(
                block_id="prod_p_0069",
                quote="Diamond Catering Package",
            )],
            confidence=Confidence.HIGH,
        )],
    )
    return staged


def test_build_profile_rag_surfaces_and_validates_a_beyond_cap_offering():
    """use_rag=True must let an offering cited from a beyond-200-cap block both
    REACH the LLM (via retrieval) and SURVIVE validation (validator sees the full
    pack). The same staged citation is rejected when RAG is off — proving the
    wiring (extractor feeds the full pack AND the validator uses it)."""
    m = _catalog_manifest()

    rag_mock = MockCaller(_staged_offering_citing_beyond_cap())
    rag_res = build_profile(m, rag_mock, use_rag=True, embed_fn=_any_embed,
                            return_details=True)
    assert len(rag_res.profile.offerings) == 1
    # the surfaced block is in the validation (full) pack
    assert "prod_p_0069" in rag_res.pack.block_ids

    norag_mock = MockCaller(_staged_offering_citing_beyond_cap())
    norag_res = build_profile(m, norag_mock, use_rag=False, return_details=True)
    assert len(norag_res.profile.offerings) == 0          # citation rejected (not in capped pack)
    assert "prod_p_0069" not in norag_res.pack.block_ids


def test_build_profile_default_is_unchanged_no_embedding():
    """Default (use_rag omitted) never embeds and behaves exactly as before —
    the offering citing the dropped block is rejected, no network touched."""
    m = _catalog_manifest()
    mock = MockCaller(_staged_offering_citing_beyond_cap())
    # embed_fn that would explode if ever called — proves the default never embeds
    def _boom(_texts):  # pragma: no cover - must not run
        raise AssertionError("embed_fn must not be called when use_rag is False")
    res = build_profile(m, mock, embed_fn=_boom, return_details=True)
    assert len(res.profile.offerings) == 0
