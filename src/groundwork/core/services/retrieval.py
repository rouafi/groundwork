"""Hybrid retrieval: vector and keyword rankings fused by Reciprocal Rank Fusion.

The fusion lives here, in the core, so it is tested without a real store. Each
ranking contributes `1 / (RRF_K + rank)` to a chunk; a chunk both searches found
rises above a chunk only one found. The result's `score` is that fused score.
"""

from collections.abc import Sequence

from groundwork.core.domain.search import SearchHit
from groundwork.core.ports.embedding import EmbeddingPort
from groundwork.core.ports.vector_store import VectorStorePort

RRF_K = 60
CANDIDATES = 20


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[SearchHit]], k: int, rrf_k: int = RRF_K
) -> tuple[SearchHit, ...]:
    """Merge best-first rankings into the top `k` hits, ties broken by chunk id."""
    scores: dict[str, float] = {}
    seen: dict[str, SearchHit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            seen.setdefault(hit.chunk_id, hit)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:k]
    return tuple(
        seen[chunk_id].model_copy(update={"score": scores[chunk_id]}) for chunk_id in ordered
    )


def search_knowhow(
    query: str,
    store: VectorStorePort,
    embedding: EmbeddingPort,
    k: int = 5,
    candidates: int = CANDIDATES,
) -> tuple[SearchHit, ...]:
    """Return the `k` best chunks for `query`, from both searches fused."""
    depth = max(candidates, k)
    (vector,) = embedding.embed([query], "query")
    return reciprocal_rank_fusion(
        [store.vector_search(vector, depth), store.keyword_search(query, depth)], k
    )
