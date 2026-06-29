"""On-the-fly RAG retriever over a scrape's text blocks (Pillar 2 / Step 2).

The LLM profile-extraction historically saw only a heuristic count-capped slice
of the scraped text (MEASURED: te.eg 153 of 1352 blocks; ~38% of post-filter
content corpus-wide — see benchmark/measure_evidence_truncation.py). This module
replaces that blind cap with PER-GROUP semantic retrieval:

    full_pack  = build_full_evidence_pack(manifest, rules_profile)  # 200-cap LIFTED
    retriever  = build_rag_retriever(manifest, rules_profile)       # embed blocks ONCE
    group_pack = retriever.retrieve(default_query_for("offerings"), k)  # top-K relevant

Each extraction group (identity / offerings / positioning / trust) retrieves the
top-K blocks most relevant to ITS intent, so the model reads the relevant context
for that group within the token budget instead of a blind score-ranked prefix.

Invariants:
- Zero-hallucination preserved: retrieved blocks keep their block_id + page_url, so
  the existing validator (which checks evidence against block_ids) is unchanged.
- Graceful degrade: no embeddings (no Gemini / API error) -> retrieve() returns the
  standard global pack (today's behavior, no regression).
- Universal: the query intents are generic marketing concepts, no vertical hacks.

This module is INERT until wired into the extractor (Step 3); building it changes
no live behavior.
"""
from __future__ import annotations

from typing import Callable, Optional

from scraper.schemas import ScrapeManifest

from ..schemas import BusinessProfile
from .embeddings import embed_texts, top_k
from .evidence_pack import EvidenceBlock, EvidencePack, build_evidence_pack

# A scrape rarely exceeds a few thousand blocks; lift the selection caps far above
# any real corpus so build_full_evidence_pack returns ALL filtered blocks (still
# scored/sorted, still deduped — only the COUNT caps are removed).
_UNCAPPED = 10_000_000

EmbedFn = Callable[[list[str]], Optional[list[list[float]]]]


def build_full_evidence_pack(
    manifest: ScrapeManifest,
    rules_profile: BusinessProfile,
) -> EvidencePack:
    """Same filter / score / dedup as build_evidence_pack, but with the 200-block
    and 60-per-page-type SELECTION caps lifted — every relevant block, for retrieval."""
    return build_evidence_pack(
        manifest,
        rules_profile,
        max_blocks=_UNCAPPED,
        max_per_page_type=_UNCAPPED,
    )


# ---------------------------------------------------------------------
# Per-group query intents (universal marketing concepts; no vertical hacks).
# text-embedding-004 is multilingual, so an English intent retrieves Arabic
# blocks cross-lingually too (to be validated live in Step 4).
# ---------------------------------------------------------------------

_GROUP_QUERIES: dict[str, str] = {
    "identity": (
        "What this business is and does: its name, tagline, mission, a description "
        "of what it provides, who it serves and where it operates, and the industry "
        "or category it belongs to."
    ),
    "offerings": (
        "The specific products, services, menu items, courses, programs, packages, "
        "collections, treatments or plans this business offers to its customers, "
        "including their names, descriptions and prices."
    ),
    "positioning": (
        "What makes this business distinctive: its value propositions and promises, "
        "the audience it speaks to, its tone of voice, competitive differentiators "
        "and any unique edge or notable facts about it."
    ),
    "trust": (
        "Proof of credibility and trust: certifications, awards, accreditations, "
        "notable clients and partners, years in business or founding date, team "
        "credentials, testimonials, guarantees, and the geographic areas it serves."
    ),
}

# Default K per group. From the Step-0 measurement the 30k-char prompt budget fits
# roughly 200 short blocks; retrieval is relevance-ranked so the top-K are the most
# relevant, and the prompt builder's as_llm_text(30_000) char cap stays as the final
# safety. K is intentionally generous (the prior global pack itself capped at 200).
DEFAULT_K = 200


def default_query_for(group: str) -> Optional[str]:
    """The retrieval intent for one extraction group, or None for an unknown group."""
    return _GROUP_QUERIES.get(group)


class RagRetriever:
    """Embed a scrape's blocks once, then serve per-group top-K relevant packs.

    On ANY embedding failure (no SDK/credential, API error, mis-counted response)
    retrieve() transparently returns `fallback_pack` — the standard 200-capped
    global pack — so a caller that always goes through retrieve() gets today's
    behavior with no special-casing. The block embedding is attempted once and the
    outcome cached (a failure is not retried per-group)."""

    def __init__(
        self,
        full_pack: EvidencePack,
        fallback_pack: EvidencePack,
        embed_fn: EmbedFn = embed_texts,
    ):
        self.full_pack = full_pack
        self.fallback_pack = fallback_pack
        self._embed_fn = embed_fn
        self._block_vecs: Optional[list[list[float]]] = None
        self._embed_attempted = False
        self._embed_ok = False

    def _ensure_block_vectors(self) -> bool:
        """Embed all full_pack block texts once. Returns True when usable vectors
        are available. Cached — a failure is remembered (no repeat API calls)."""
        if self._embed_attempted:
            return self._embed_ok
        self._embed_attempted = True
        blocks = self.full_pack.blocks
        if not blocks:
            return False
        vecs = self._embed_fn([b.text for b in blocks])
        if not vecs or len(vecs) != len(blocks):
            return False
        self._block_vecs = vecs
        self._embed_ok = True
        return True

    def retrieve(self, query: str, k: int = DEFAULT_K) -> EvidencePack:
        """Return an EvidencePack of the top-K blocks most relevant to `query`.
        Falls back to the global pack when embeddings are unavailable."""
        if not self._ensure_block_vectors():
            return self.fallback_pack
        qvecs = self._embed_fn([query])
        if not qvecs:
            return self.fallback_pack
        idxs = top_k(qvecs[0], self._block_vecs, k)
        if not idxs:
            return self.fallback_pack
        chosen = [self.full_pack.blocks[i] for i in idxs]
        return _pack_with_blocks(self.full_pack, chosen)


def _pack_with_blocks(src: EvidencePack, blocks: list[EvidenceBlock]) -> EvidencePack:
    """Build a per-group pack from a subset of `src`'s blocks: copy metadata and
    recompute diagnostics. Provenance (block_id / page_url / verbatim text) preserved."""
    return EvidencePack(
        source_url=src.source_url,
        languages=list(src.languages),
        blocks=blocks,
        blocks_total_in_manifest=src.blocks_total_in_manifest,
        blocks_after_filter=src.blocks_after_filter,
        block_count=len(blocks),
        block_ids=[b.block_id for b in blocks],
        page_type_distribution=_dist(blocks, "page_type"),
        section_distribution=_dist(blocks, "section"),
        vertical_rerank_category=src.vertical_rerank_category,
        missing_fields=list(src.missing_fields),
    )


def _dist(blocks: list[EvidenceBlock], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for b in blocks:
        v = getattr(b, attr)
        out[v] = out.get(v, 0) + 1
    return out


def build_rag_retriever(
    manifest: ScrapeManifest,
    rules_profile: BusinessProfile,
    embed_fn: EmbedFn = embed_texts,
) -> RagRetriever:
    """Construct a retriever for a scrape: a full (uncapped) pack for retrieval +
    the standard global pack for graceful fallback. Both reuse the existing
    filter/score/dedup builder (no logic duplication)."""
    full_pack = build_full_evidence_pack(manifest, rules_profile)
    fallback_pack = build_evidence_pack(manifest, rules_profile)
    return RagRetriever(full_pack, fallback_pack, embed_fn=embed_fn)
