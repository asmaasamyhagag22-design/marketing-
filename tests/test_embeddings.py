"""Hermetic tests for the embeddings helper (Pillar 2 / Step 1).

No network: cosine/top_k are pure stdlib; embed_texts is exercised with an
injected fake client (the same provider-injection discipline as the MockCaller /
FakeProvider tests). The live text-embedding-004 path is out-of-CI.
"""
from __future__ import annotations

import math

from business_profile.llm.embeddings import cosine, top_k, embed_texts


# ---------------------------------------------------------------------
# cosine
# ---------------------------------------------------------------------

def test_cosine_identical_is_one():
    v = [1.0, 2.0, 3.0]
    assert math.isclose(cosine(v, v), 1.0, rel_tol=1e-9)


def test_cosine_orthogonal_is_zero():
    assert math.isclose(cosine([1.0, 0.0], [0.0, 1.0]), 0.0, abs_tol=1e-9)


def test_cosine_opposite_is_minus_one():
    assert math.isclose(cosine([1.0, 1.0], [-1.0, -1.0]), -1.0, rel_tol=1e-9)


def test_cosine_degenerate_inputs_return_zero():
    assert cosine([], [1.0]) == 0.0
    assert cosine([1.0, 2.0], [1.0]) == 0.0      # length mismatch
    assert cosine([0.0, 0.0], [1.0, 2.0]) == 0.0  # zero-norm


# ---------------------------------------------------------------------
# top_k
# ---------------------------------------------------------------------

def test_top_k_ranks_by_similarity_best_first():
    query = [1.0, 0.0]
    vecs = [
        [0.0, 1.0],   # 0: orthogonal     (cos 0)
        [1.0, 0.0],   # 1: identical      (cos 1)  <- best
        [0.7, 0.3],   # 2: close          (cos ~0.92)
        [-1.0, 0.0],  # 3: opposite       (cos -1)
    ]
    assert top_k(query, vecs, 2) == [1, 2]
    assert top_k(query, vecs, 4) == [1, 2, 0, 3]


def test_top_k_bounds_and_bad_input():
    query = [1.0, 0.0]
    vecs = [[1.0, 0.0], [0.0, 1.0]]
    assert top_k(query, vecs, 10) == [0, 1]   # k > len -> all
    assert top_k(query, vecs, 0) == []
    assert top_k([], vecs, 2) == []
    assert top_k(query, [], 2) == []


def test_top_k_tie_breaks_by_lower_index():
    query = [1.0, 0.0]
    vecs = [[1.0, 0.0], [2.0, 0.0]]  # both cos 1.0 with query
    assert top_k(query, vecs, 2) == [0, 1]


# ---------------------------------------------------------------------
# embed_texts (injected fake client — no network)
# ---------------------------------------------------------------------

class _FakeEmbeddings:
    def __init__(self, values_list):
        self.embeddings = [type("E", (), {"values": v})() for v in values_list]


class _FakeModels:
    def __init__(self, fn):
        self._fn = fn
        self.calls = []

    def embed_content(self, model, contents):
        self.calls.append((model, list(contents)))
        return self._fn(contents)


class _FakeClient:
    def __init__(self, fn):
        self.models = _FakeModels(fn)


def _deterministic(contents):
    # one 2-d vector per input: (len(text), number of words)
    return _FakeEmbeddings([[float(len(t)), float(len(t.split()))] for t in contents])


def test_embed_texts_empty_returns_empty_list():
    assert embed_texts([]) == []  # empty -> [] (not None), never calls the SDK


def test_embed_texts_returns_aligned_vectors():
    client = _FakeClient(_deterministic)
    out = embed_texts(["a", "bb cc"], client=client)
    assert out == [[1.0, 1.0], [5.0, 2.0]]


def test_embed_texts_batches_and_preserves_order():
    client = _FakeClient(_deterministic)
    texts = ["a", "bb", "ccc", "dddd", "eeeee"]
    out = embed_texts(texts, batch_size=2, client=client)
    assert out == [[float(len(t)), 1.0] for t in texts]
    # 5 items / batch 2 -> 3 calls, chunked in order
    assert [c[1] for c in client.models.calls] == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]


def test_embed_texts_returns_none_on_api_error():
    def boom(contents):
        raise RuntimeError("simulated API failure")
    out = embed_texts(["x"], client=_FakeClient(boom))
    assert out is None  # graceful degrade, never raises


def test_embed_texts_returns_none_on_count_mismatch():
    # SDK returns fewer vectors than inputs -> treat the whole batch as failed
    client = _FakeClient(lambda contents: _FakeEmbeddings([[1.0, 1.0]]))
    out = embed_texts(["x", "y"], client=client)
    assert out is None
