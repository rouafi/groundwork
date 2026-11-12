"""EmbeddingPort contract: one suite, every adapter that can run without the network.

Written against the port only. To cover a new adapter, add a factory to `ADAPTERS`.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from groundwork.adapters.embedding.replay import (
    EmbeddingRecordings,
    RecordingEmbedding,
    ReplayEmbedding,
)
from groundwork.core.ports.embedding import EmbeddingPort
from tests.fakes import HashEmbedding

MODEL = "fake-model"
TEXTS = ["We keep emails short.", "Discounts are discussed on the phone.", "Prices are exact."]


def _replay(directory: Path) -> EmbeddingPort:
    """Record the fake's vectors for the texts of this suite, then serve them on replay."""
    recordings = EmbeddingRecordings(directory)
    recorder = RecordingEmbedding(HashEmbedding(), recordings, MODEL)
    for input_type in ("document", "query"):
        recorder.embed(TEXTS, input_type)  # type: ignore[arg-type]
    return ReplayEmbedding(recordings, MODEL)


ADAPTERS: dict[str, Callable[[Path], EmbeddingPort]] = {
    "hash": lambda _: HashEmbedding(),
    "replay": _replay,
}


@pytest.fixture(params=sorted(ADAPTERS))
def embedding(request: pytest.FixtureRequest, tmp_path: Path) -> EmbeddingPort:
    return ADAPTERS[request.param](tmp_path)


def test_one_vector_per_text_in_the_input_order(embedding: EmbeddingPort) -> None:
    vectors = embedding.embed(TEXTS, "document")
    assert len(vectors) == len(TEXTS)
    assert vectors[0] != vectors[1] != vectors[2]
    assert vectors == [embedding.embed([t], "document")[0] for t in TEXTS]


def test_no_text_gives_no_vector(embedding: EmbeddingPort) -> None:
    assert embedding.embed([], "document") == []


def test_every_vector_has_the_same_length(embedding: EmbeddingPort) -> None:
    assert len({len(v) for v in embedding.embed(TEXTS, "query")}) == 1


def test_the_same_text_and_type_give_the_same_vector(embedding: EmbeddingPort) -> None:
    assert embedding.embed(TEXTS, "query") == embedding.embed(TEXTS, "query")


def test_a_query_and_a_document_are_embedded_apart(embedding: EmbeddingPort) -> None:
    assert embedding.embed(TEXTS[:1], "query") != embedding.embed(TEXTS[:1], "document")
