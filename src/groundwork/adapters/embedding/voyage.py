"""VoyageEmbedding: the EmbeddingPort on the Voyage AI API.

Documents and queries are embedded differently (`input_type`), as Voyage advises for
retrieval. The model id is the single constant below; it is part of every recording
key, so changing it invalidates the recorded vectors.
"""

from collections.abc import Sequence
from typing import Any

from voyageai.error import VoyageError

from groundwork.core.domain.errors import ModelError
from groundwork.core.ports.embedding import InputType

VOYAGE_MODEL = "voyage-4"
BATCH_SIZE = 128


class VoyageEmbedding:
    def __init__(self, client: Any, model: str = VOYAGE_MODEL) -> None:
        self._client = client
        self.model = model

    def embed(self, texts: Sequence[str], input_type: InputType) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = list(texts[start : start + BATCH_SIZE])
            try:
                result = self._client.embed(batch, model=self.model, input_type=input_type)
            except VoyageError as exc:
                raise ModelError(f"Voyage API call failed: {exc}") from exc
            if len(result.embeddings) != len(batch):
                raise ModelError(
                    f"Voyage returned {len(result.embeddings)} vectors for {len(batch)} texts"
                )
            vectors.extend([float(x) for x in vector] for vector in result.embeddings)
        return vectors
