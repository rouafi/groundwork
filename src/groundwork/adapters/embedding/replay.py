"""Record and replay embeddings.

`RecordingEmbedding` wraps any EmbeddingPort and writes each vector it serves.
`ReplayEmbedding` serves those recordings: no network, never a live fallback. The key
is the sha256 of the model id, the input type and the text, so what one writes the
other reads, and editing a text or changing the model invalidates the recording.
"""

import json
from collections.abc import Sequence
from pathlib import Path

from groundwork.adapters.model.recording import call_key
from groundwork.core.domain.errors import EmbeddingMissError
from groundwork.core.ports.embedding import EmbeddingPort, InputType


def embedding_key(model: str, input_type: InputType, text: str) -> str:
    return call_key({"model": model, "input_type": input_type, "text": text})


class EmbeddingRecordings:
    """One JSON file per embedded text under a pack's `embeddings` trace directory."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path(self, key: str) -> Path:
        return self._directory / f"{key}.json"

    def read(self, key: str) -> list[float]:
        path = self.path(key)
        if not path.is_file():
            raise EmbeddingMissError(key, str(path))
        record = json.loads(path.read_text(encoding="utf-8"))
        return [float(x) for x in record["vector"]]

    def save(self, model: str, input_type: InputType, text: str, vector: Sequence[float]) -> None:
        key = embedding_key(model, input_type, text)
        record = {
            "request": {"model": model, "input_type": input_type, "text": text},
            "vector": list(vector),
        }
        self._directory.mkdir(parents=True, exist_ok=True)
        body = json.dumps(record, sort_keys=True, indent=None, ensure_ascii=False)
        self.path(key).write_text(body + "\n", encoding="utf-8")


class ReplayEmbedding:
    """An EmbeddingPort backed by recordings. A missing one raises `EmbeddingMissError`."""

    def __init__(self, recordings: EmbeddingRecordings, model: str) -> None:
        self._recordings = recordings
        self._model = model

    def embed(self, texts: Sequence[str], input_type: InputType) -> list[list[float]]:
        return [self._recordings.read(embedding_key(self._model, input_type, t)) for t in texts]


class RecordingEmbedding:
    """Serve from `inner` and record every vector, for later replay."""

    def __init__(self, inner: EmbeddingPort, recordings: EmbeddingRecordings, model: str) -> None:
        self._inner = inner
        self._recordings = recordings
        self._model = model

    def embed(self, texts: Sequence[str], input_type: InputType) -> list[list[float]]:
        vectors = self._inner.embed(texts, input_type)
        for text, vector in zip(texts, vectors, strict=True):
            self._recordings.save(self._model, input_type, text, vector)
        return vectors
