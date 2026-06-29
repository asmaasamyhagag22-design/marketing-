"""Gemini text embeddings + pure-Python cosine retrieval (Pillar 2 / Step 1).

A side-effect-free helper for semantic retrieval over a scrape's text blocks.
Same discipline as the other data-fetch helpers (competitor/search_providers.py,
scraper/deep_search.py): NEVER raises (any failure -> None), no .env / os.environ
mutation, lazy SDK import, and NO new dependency — it reuses the already-pinned
`google-genai` Vertex/ADC path that GeminiCaller / Imagen / Veo already use.

Public surface:
    embed_texts(texts, *, model=None, batch_size=100, client=None)
        -> list[list[float]] | None
    cosine(a, b) -> float
    top_k(query_vec, vecs, k) -> list[int]

A scrape is a few hundred to low-thousand blocks, so pure-Python cosine over the
per-scrape vectors is trivial — no numpy / ChromaDB (honors "no new heavy deps").
The retriever (Step 2) embeds all blocks ONCE, then ranks per extraction group.
"""
from __future__ import annotations

import math
import os
from typing import Optional

# Vertex / AI-Studio embedding model. text-embedding-004 is cheap and runs on the
# same GCP credits as the rest of the Gemini pipeline. Override with EMBEDDING_MODEL.
DEFAULT_EMBEDDING_MODEL = "text-embedding-004"
_DEFAULT_BATCH = 100  # Vertex text-embedding-004 allows up to 250 instances/request


def _build_client():
    """Build a google-genai client the SAME way GeminiCaller does — Vertex by
    default (GOOGLE_CLOUD_PROJECT + ADC), or AI-Studio when an explicit Gemini
    key is set. Returns None when the SDK or a credential is missing. Never raises.
    """
    try:
        from google import genai
    except Exception:
        return None
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    try:
        if api_key:
            return genai.Client(api_key=api_key)
        if project:
            return genai.Client(vertexai=True, project=project, location=location)
    except Exception:
        return None
    return None


def _vectors_from_response(resp) -> Optional[list[list[float]]]:
    """Pull the float vectors out of a google-genai embed_content response,
    tolerant of SDK shape differences (.embeddings[].values, or a dict)."""
    embeddings = getattr(resp, "embeddings", None)
    if embeddings is None and isinstance(resp, dict):
        embeddings = resp.get("embeddings")
    if embeddings is None:
        return None
    out: list[list[float]] = []
    for e in embeddings:
        values = getattr(e, "values", None)
        if values is None and isinstance(e, dict):
            values = e.get("values")
        if values is None:
            return None
        out.append([float(x) for x in values])
    return out


def embed_texts(
    texts,
    *,
    model: Optional[str] = None,
    batch_size: int = _DEFAULT_BATCH,
    client=None,
) -> Optional[list[list[float]]]:
    """Embed `texts` with Gemini text-embedding-004 (batched).

    Returns a list of vectors aligned 1:1 with `texts` (an empty list for empty
    input), or None on ANY failure (no SDK, no credential, API error, or a
    malformed / mis-counted response) so callers degrade to the non-RAG path.
    Never raises. `client` is injectable for tests.
    """
    items = [t if isinstance(t, str) else str(t) for t in texts]
    if not items:
        return []
    model = model or os.environ.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
    cli = client if client is not None else _build_client()
    if cli is None:
        return None
    out: list[list[float]] = []
    try:
        step = max(1, batch_size)
        for start in range(0, len(items), step):
            chunk = items[start:start + step]
            resp = cli.models.embed_content(model=model, contents=chunk)
            vecs = _vectors_from_response(resp)
            if vecs is None or len(vecs) != len(chunk):
                return None
            out.extend(vecs)
    except Exception:
        return None
    if len(out) != len(items):
        return None
    return out


def cosine(a, b) -> float:
    """Cosine similarity of two equal-length vectors. 0.0 on degenerate input
    (empty, mismatched length, or a zero-norm vector)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def top_k(query_vec, vecs, k: int) -> list[int]:
    """Indices of the `k` vectors most cosine-similar to `query_vec`, best first.
    Ties break by lower index (stable — prefers earlier blocks). [] on bad input."""
    if not query_vec or not vecs or k <= 0:
        return []
    scored = [(cosine(query_vec, v), i) for i, v in enumerate(vecs)]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [i for _score, i in scored[:k]]
