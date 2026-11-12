"""LanceDbStore: a VectorStorePort on LanceDB, with native full-text search.

The database lives in a directory the caller owns, or in a temporary one that goes
away with the store: indexes are rebuilt from `chunks.jsonl` at start, never kept.
A search reads every row's score and sorts, so ties are ordered by chunk id as the
contract demands; this is meant for the small corpora of a client pack.
"""

import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import lancedb
from lancedb.index import FTS

from groundwork.core.domain.search import Chunk, SearchHit

_TABLE = "chunks"
_TEXT = "indexed_text"


class LanceDbStore:
    def __init__(self, path: Path | None = None) -> None:
        self._scratch = None if path else tempfile.TemporaryDirectory(prefix="groundwork-lance-")
        self._db = lancedb.connect(str(path or self._scratch.name))  # type: ignore[union-attr]
        self._table: Any = None
        self._size = 0

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        if not chunks:
            return
        for chunk in chunks:
            if not chunk.embedding:
                raise ValueError(f"chunk {chunk.id!r} has no embedding")
        sizes = {len(c.embedding) for c in chunks} | ({self._size} if self._size else set())
        if len(sizes) > 1:
            raise ValueError(f"embeddings must all have one size, got {sorted(sizes)}")
        rows = [_row(c) for c in chunks]
        if self._table is None:
            self._table = self._db.create_table(_TABLE, data=rows, mode="overwrite")
            self._size = len(chunks[0].embedding)
        else:
            (
                self._table.merge_insert("id")
                .when_matched_update_all()
                .when_not_matched_insert_all()
                .execute(rows)
            )
        self._table.create_index(_TEXT, config=FTS(), replace=True)

    def vector_search(self, embedding: Sequence[float], k: int) -> tuple[SearchHit, ...]:
        _check_k(k)
        if self._table is None:
            return ()
        if len(embedding) != self._size:
            raise ValueError(
                f"query has {len(embedding)} values, the stored embeddings have {self._size}"
            )
        rows = (
            self._table.search(list(embedding))
            .metric("cosine")
            .limit(self._table.count_rows())
            .to_list()
        )
        return _top([(1.0 - row["_distance"], row) for row in rows], k)

    def keyword_search(self, query: str, k: int) -> tuple[SearchHit, ...]:
        _check_k(k)
        if self._table is None or not query.strip():
            return ()
        rows = self._table.search(query, query_type="fts").limit(self._table.count_rows()).to_list()
        return _top([(row["_score"], row) for row in rows], k)


def _row(chunk: Chunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "doc_id": chunk.doc_id,
        "text": chunk.text,
        _TEXT: chunk.indexed_text,
        "vector": list(chunk.embedding),
    }


def _check_k(k: int) -> None:
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")


def _top(scored: list[tuple[float, dict[str, Any]]], k: int) -> tuple[SearchHit, ...]:
    ranked = sorted(scored, key=lambda item: (-item[0], item[1]["id"]))[:k]
    return tuple(
        SearchHit(chunk_id=row["id"], doc_id=row["doc_id"], text=row["text"], score=score)
        for score, row in ranked
    )
