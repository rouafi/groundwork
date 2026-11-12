"""VectorStorePort contract: one suite, every adapter.

Written against the port only. To cover a new adapter, add a factory to `ADAPTERS`.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from groundwork.adapters.vector.lance import LanceDbStore
from groundwork.adapters.vector.memory import InMemoryVectorStore
from groundwork.core.domain.search import Chunk
from groundwork.core.ports.vector_store import VectorStorePort

ADAPTERS: dict[str, Callable[[Path], VectorStorePort]] = {
    "memory": lambda _: InMemoryVectorStore(),
    "lancedb": lambda tmp_path: LanceDbStore(tmp_path / "lance"),
}


@pytest.fixture(params=sorted(ADAPTERS))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> VectorStorePort:
    return ADAPTERS[request.param](tmp_path)


def _chunk(
    id: str, text: str, embedding: tuple[float, ...], context: str = "", doc_id: str = "doc-1"
) -> Chunk:
    return Chunk(
        id=id, doc_id=doc_id, role="expert", text=text, context=context, embedding=embedding
    )


@pytest.fixture
def loaded(store: VectorStorePort) -> VectorStorePort:
    store.upsert(
        [
            _chunk("c-1", "We keep emails short and friendly.", (1.0, 0.0, 0.0)),
            _chunk("c-2", "Discounts are discussed on the phone.", (0.0, 1.0, 0.0)),
            _chunk("c-3", "Prices come from the catalog.", (0.7, 0.7, 0.0)),
        ]
    )
    return store


def test_searching_an_empty_store_returns_nothing(store: VectorStorePort) -> None:
    assert store.vector_search((1.0, 0.0, 0.0), 3) == ()
    assert store.keyword_search("emails", 3) == ()


def test_vector_search_ranks_by_cosine_similarity(loaded: VectorStorePort) -> None:
    hits = loaded.vector_search((1.0, 0.1, 0.0), 3)
    assert [h.chunk_id for h in hits] == ["c-1", "c-3", "c-2"]
    assert hits[0].score > hits[1].score > hits[2].score


def test_vector_search_returns_at_most_k_and_every_chunk_when_k_is_large(
    loaded: VectorStorePort,
) -> None:
    assert len(loaded.vector_search((1.0, 0.0, 0.0), 2)) == 2
    assert len(loaded.vector_search((1.0, 0.0, 0.0), 50)) == 3


def test_equal_scores_are_ordered_by_chunk_id(store: VectorStorePort) -> None:
    store.upsert([_chunk("c-b", "same", (1.0, 0.0)), _chunk("c-a", "same", (1.0, 0.0))])
    assert [h.chunk_id for h in store.vector_search((1.0, 0.0), 2)] == ["c-a", "c-b"]


def test_upsert_replaces_a_chunk_with_the_same_id(loaded: VectorStorePort) -> None:
    loaded.upsert([_chunk("c-1", "A new text about quotes.", (1.0, 0.0, 0.0))])
    hits = loaded.vector_search((1.0, 0.0, 0.0), 10)
    assert [h.chunk_id for h in hits].count("c-1") == 1
    assert next(h for h in hits if h.chunk_id == "c-1").text == "A new text about quotes."
    assert loaded.keyword_search("friendly", 5) == ()


def test_keyword_search_returns_only_chunks_that_share_a_word(loaded: VectorStorePort) -> None:
    hits = loaded.keyword_search("catalog prices", 5)
    assert [h.chunk_id for h in hits] == ["c-3"]
    assert loaded.keyword_search("blockchain", 5) == ()


def test_keyword_search_ranks_more_matching_words_first(store: VectorStorePort) -> None:
    store.upsert(
        [
            _chunk("c-1", "Discounts are discussed on the phone.", (1.0, 0.0)),
            _chunk("c-2", "Discounts never go in writing, discounts stay verbal.", (0.0, 1.0)),
            _chunk("c-3", "Phone calls happen on Thursday.", (1.0, 1.0)),
        ]
    )
    hits = store.keyword_search("discounts phone", 3)
    assert hits[0].chunk_id == "c-1"
    assert {h.chunk_id for h in hits} == {"c-1", "c-2", "c-3"}


def test_keyword_search_matches_the_context_but_a_hit_shows_the_text(
    store: VectorStorePort,
) -> None:
    store.upsert(
        [
            _chunk("c-1", "We never do that in writing.", (1.0, 0.0), context="About discounts."),
            _chunk("c-2", "Unrelated text.", (0.0, 1.0)),
        ]
    )
    (hit,) = store.keyword_search("discounts", 5)
    assert hit.chunk_id == "c-1"
    assert hit.text == "We never do that in writing."


def test_keyword_search_is_not_case_sensitive(loaded: VectorStorePort) -> None:
    assert [h.chunk_id for h in loaded.keyword_search("CATALOG", 5)] == ["c-3"]


def test_hits_carry_the_document_id(store: VectorStorePort) -> None:
    store.upsert([_chunk("c-1", "Text.", (1.0, 0.0), doc_id="acme-i-2")])
    assert store.vector_search((1.0, 0.0), 1)[0].doc_id == "acme-i-2"


def test_a_chunk_without_an_embedding_is_rejected(store: VectorStorePort) -> None:
    with pytest.raises(ValueError, match="embedding"):
        store.upsert([_chunk("c-1", "Text.", ())])


def test_embeddings_of_different_sizes_are_rejected(loaded: VectorStorePort) -> None:
    with pytest.raises(ValueError, match="size"):
        loaded.upsert([_chunk("c-9", "Text.", (1.0, 0.0))])


@pytest.mark.parametrize("k", [0, -1])
def test_k_must_be_positive(loaded: VectorStorePort, k: int) -> None:
    with pytest.raises(ValueError, match="k"):
        loaded.vector_search((1.0, 0.0, 0.0), k)
    with pytest.raises(ValueError, match="k"):
        loaded.keyword_search("emails", k)
