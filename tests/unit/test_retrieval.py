from collections.abc import Sequence

import pytest

from groundwork.adapters.vector.memory import InMemoryVectorStore
from groundwork.core.domain.search import Chunk, SearchHit
from groundwork.core.services.retrieval import (
    RRF_K,
    reciprocal_rank_fusion,
    search_knowhow,
)


def _hits(*ids: str) -> list[SearchHit]:
    return [SearchHit(chunk_id=i, doc_id="d", text=f"text {i}", score=0.0) for i in ids]


def test_fusion_order_matches_the_hand_computed_scores() -> None:
    # A ranks a, b, c; B ranks b, c, d (rrf_k = 60):
    #   b = 1/62 + 1/61 = 0.032522    c = 1/63 + 1/62 = 0.032002
    #   a = 1/61        = 0.016393    d = 1/63        = 0.015873
    fused = reciprocal_rank_fusion([_hits("a", "b", "c"), _hits("b", "c", "d")], k=4)
    assert [h.chunk_id for h in fused] == ["b", "c", "a", "d"]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1].score == pytest.approx(1 / 63 + 1 / 62)
    assert fused[2].score == pytest.approx(1 / 61)
    assert fused[3].score == pytest.approx(1 / 63)


def test_fusion_returns_at_most_k_and_equal_scores_by_chunk_id() -> None:
    fused = reciprocal_rank_fusion([_hits("b"), _hits("a")], k=1)
    assert [h.chunk_id for h in fused] == ["a"]


def test_fusion_of_nothing_is_nothing() -> None:
    assert reciprocal_rank_fusion([], k=5) == ()
    assert reciprocal_rank_fusion([[], []], k=5) == ()


def test_fusion_keeps_the_text_and_document_of_the_hit() -> None:
    (hit,) = reciprocal_rank_fusion([_hits("a")], k=1)
    assert (hit.doc_id, hit.text) == ("d", "text a")
    assert RRF_K == 60


class QueryEmbedding:
    """Maps known queries to fixed vectors, so the test controls the vector ranking."""

    def __init__(self, vector: list[float]) -> None:
        self.vector = vector
        self.calls: list[tuple[list[str], str]] = []

    def embed(self, texts: Sequence[str], input_type: str) -> list[list[float]]:
        self.calls.append((list(texts), input_type))
        return [self.vector for _ in texts]


def _store() -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    store.upsert(
        [
            Chunk(
                id="c-1",
                doc_id="d-1",
                role="r",
                text="Discounts go by phone.",
                embedding=(1.0, 0.0),
            ),
            Chunk(
                id="c-2", doc_id="d-1", role="r", text="Keep emails short.", embedding=(0.0, 1.0)
            ),
            Chunk(
                id="c-3", doc_id="d-2", role="r", text="Catalog prices only.", embedding=(0.7, 0.7)
            ),
        ]
    )
    return store


def test_a_chunk_found_by_both_searches_ranks_first() -> None:
    # Vector order: c-1, c-3, c-2. Keyword "discounts" matches only c-1.
    hits = search_knowhow("discounts", _store(), QueryEmbedding([1.0, 0.1]), k=3)
    assert hits[0].chunk_id == "c-1"
    assert {h.chunk_id for h in hits} == {"c-1", "c-2", "c-3"}


def test_a_chunk_only_the_keyword_search_finds_is_still_returned() -> None:
    hits = search_knowhow("short", _store(), QueryEmbedding([1.0, 0.0]), k=3)
    assert "c-2" in [h.chunk_id for h in hits[:2]]


def test_the_query_is_embedded_as_a_query_and_k_limits_the_result() -> None:
    embedding = QueryEmbedding([1.0, 0.0])
    hits = search_knowhow("discounts", _store(), embedding, k=1)
    assert embedding.calls == [(["discounts"], "query")]
    assert len(hits) == 1
