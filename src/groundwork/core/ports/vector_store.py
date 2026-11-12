"""VectorStorePort: store chunks and rank them by vector or by keyword.

Fusing the two rankings is the core's job (services/retrieval.py), so a store only
has to answer each search on its own.

Contract (tests/contracts/test_vector_store_contract.py, run against every adapter):
- `upsert` replaces a chunk with the same id and never duplicates it.
- Both searches return at most `k` hits, best first, ties broken by chunk id.
- `vector_search` ranks by cosine similarity and returns a hit for every stored
  chunk up to `k`.
- `keyword_search` returns only chunks that share a word with the query, and
  nothing when none does.
- A hit carries the chunk's `text`, not its context.
- Searching an empty store returns no hits.
"""

from collections.abc import Sequence
from typing import Protocol

from groundwork.core.domain.search import Chunk, SearchHit


class VectorStorePort(Protocol):
    """What the core may ask a store of embedded chunks."""

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        """Add or replace chunks. Each chunk must carry an embedding of the store's size."""

    def vector_search(self, embedding: Sequence[float], k: int) -> tuple[SearchHit, ...]:
        """Return the `k` chunks closest to `embedding`."""

    def keyword_search(self, query: str, k: int) -> tuple[SearchHit, ...]:
        """Return the `k` chunks whose indexed text best matches the words of `query`."""
