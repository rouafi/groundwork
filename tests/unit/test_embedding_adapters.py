import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from voyageai.error import AuthenticationError

from groundwork.adapters.embedding.replay import (
    EmbeddingRecordings,
    RecordingEmbedding,
    ReplayEmbedding,
    embedding_key,
)
from groundwork.adapters.embedding.voyage import BATCH_SIZE, VOYAGE_MODEL, VoyageEmbedding
from groundwork.core.domain.errors import EmbeddingMissError, ModelError
from tests.fakes import HashEmbedding


class FakeVoyageClient:
    def __init__(self, *, short: bool = False, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._short = short
        self._error = error

    def embed(self, texts: list[str], model: str, input_type: str) -> Any:
        self.calls.append({"texts": texts, "model": model, "input_type": input_type})
        if self._error:
            raise self._error
        count = len(texts) - 1 if self._short else len(texts)
        return SimpleNamespace(embeddings=[[float(len(t)), 0.5] for t in texts[:count]])


def test_voyage_sends_the_model_and_input_type_and_keeps_the_order() -> None:
    client = FakeVoyageClient()
    vectors = VoyageEmbedding(client).embed(["a", "bbb"], "query")
    assert vectors == [[1.0, 0.5], [3.0, 0.5]]
    assert client.calls == [{"texts": ["a", "bbb"], "model": VOYAGE_MODEL, "input_type": "query"}]


def test_voyage_batches_large_inputs() -> None:
    client = FakeVoyageClient()
    texts = [f"t{i}" for i in range(BATCH_SIZE * 2 + 5)]
    vectors = VoyageEmbedding(client).embed(texts, "document")
    assert [len(c["texts"]) for c in client.calls] == [BATCH_SIZE, BATCH_SIZE, 5]
    assert len(vectors) == len(texts)


def test_voyage_api_errors_become_model_errors() -> None:
    client = FakeVoyageClient(error=AuthenticationError("bad key"))
    with pytest.raises(ModelError, match="Voyage API call failed"):
        VoyageEmbedding(client).embed(["a"], "document")


def test_voyage_refuses_a_response_with_a_missing_vector() -> None:
    with pytest.raises(ModelError, match="1 vectors for 2 texts"):
        VoyageEmbedding(FakeVoyageClient(short=True)).embed(["a", "b"], "document")


def test_a_replay_miss_names_the_key_and_both_ways_out(tmp_path: Path) -> None:
    replay = ReplayEmbedding(EmbeddingRecordings(tmp_path), "m")
    key = embedding_key("m", "query", "hello")
    with pytest.raises(EmbeddingMissError) as miss:
        replay.embed(["hello"], "query")
    assert key in str(miss.value)
    assert "retrieval questions" in str(miss.value)
    assert "GROUNDWORK_EMBEDDING=voyage and VOYAGE_API_KEY" in str(miss.value)
    assert "GROUNDWORK_RECORD=1" in str(miss.value)


def test_the_key_depends_on_model_type_and_text() -> None:
    keys = {
        embedding_key("m", "query", "x"),
        embedding_key("n", "query", "x"),
        embedding_key("m", "document", "x"),
        embedding_key("m", "query", "y"),
    }
    assert len(keys) == 4


def test_recording_then_replaying_returns_the_same_vectors(tmp_path: Path) -> None:
    recordings = EmbeddingRecordings(tmp_path)
    recorded = RecordingEmbedding(HashEmbedding(), recordings, "m").embed(["a", "b"], "document")
    assert ReplayEmbedding(recordings, "m").embed(["a", "b"], "document") == recorded


def test_a_recording_holds_the_request_and_the_vector_but_no_secret(tmp_path: Path) -> None:
    recordings = EmbeddingRecordings(tmp_path)
    RecordingEmbedding(HashEmbedding(), recordings, "m").embed(["a"], "query")
    (path,) = tmp_path.glob("*.json")
    record = json.loads(path.read_text())
    assert set(record) == {"request", "vector"}
    assert record["request"] == {"model": "m", "input_type": "query", "text": "a"}
