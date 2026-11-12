"""InMemoryVectorStore: a VectorStorePort with no dependency, for tests and small packs.

Vector search is exact cosine similarity; keyword search is BM25 over the words of
each chunk's indexed text (context, then chunk).
"""

import math
import re
from collections import Counter
from collections.abc import Sequence

from groundwork.core.domain.search import Chunk, SearchHit

_WORD = re.compile(r"\w+")
_K1 = 1.5
_B = 0.75


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        self._words: dict[str, Counter[str]] = {}

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        for chunk in chunks:
            if not chunk.embedding:
                raise ValueError(f"chunk {chunk.id!r} has no embedding")
        sizes = {len(c.embedding) for c in chunks} | {
            len(c.embedding) for c in self._chunks.values()
        }
        if len(sizes) > 1:
            raise ValueError(f"embeddings must all have one size, got {sorted(sizes)}")
        for chunk in chunks:
            self._chunks[chunk.id] = chunk
            self._words[chunk.id] = Counter(_tokens(chunk.indexed_text))

    def vector_search(self, embedding: Sequence[float], k: int) -> tuple[SearchHit, ...]:
        _check_k(k)
        scored = []
        for chunk in self._chunks.values():
            if len(chunk.embedding) != len(embedding):
                raise ValueError(
                    f"query has {len(embedding)} values, the stored embeddings have "
                    f"{len(chunk.embedding)}"
                )
            scored.append((_cosine(embedding, chunk.embedding), chunk))
        return _top(scored, k)

    def keyword_search(self, query: str, k: int) -> tuple[SearchHit, ...]:
        _check_k(k)
        terms = set(_tokens(query))
        if not self._chunks or not terms:
            return ()
        average = sum(sum(w.values()) for w in self._words.values()) / len(self._words)
        scored = []
        for chunk_id, words in self._words.items():
            score = sum(self._bm25(term, words, average) for term in terms if term in words)
            if score > 0:
                scored.append((score, self._chunks[chunk_id]))
        return _top(scored, k)

    def _bm25(self, term: str, words: Counter[str], average: float) -> float:
        containing = sum(1 for w in self._words.values() if term in w)
        idf = math.log(1 + (len(self._words) - containing + 0.5) / (containing + 0.5))
        frequency = words[term]
        length = sum(words.values())
        return idf * frequency * (_K1 + 1) / (frequency + _K1 * (1 - _B + _B * length / average))


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.casefold())


def _check_k(k: int) -> None:
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0


def _top(scored: list[tuple[float, Chunk]], k: int) -> tuple[SearchHit, ...]:
    ranked = sorted(scored, key=lambda item: (-item[0], item[1].id))[:k]
    return tuple(
        SearchHit(chunk_id=c.id, doc_id=c.doc_id, text=c.text, score=score) for score, c in ranked
    )
