"""VoyageEmbedding: the EmbeddingPort on the Voyage AI API.

Documents and queries are embedded differently (`input_type`), as Voyage advises for
retrieval. The model id is the single constant below; it is part of every recording
key, so changing it invalidates the recorded vectors.
"""

import time
from collections.abc import Callable, Sequence
from typing import Any

from voyageai.error import VoyageError

from groundwork.core.domain.errors import ModelError
from groundwork.core.ports.embedding import InputType

VOYAGE_MODEL = "voyage-4"
BATCH_SIZE = 128


class VoyageEmbedding:
    """`requests_per_minute` paces the calls for accounts on Voyage's reduced free limits
    (3 a minute): each call waits until one interval has passed since the previous one."""

    def __init__(
        self,
        client: Any,
        model: str = VOYAGE_MODEL,
        requests_per_minute: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self.model = model
        self._interval = 60.0 / requests_per_minute if requests_per_minute else 0.0
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None

    def _pace(self) -> None:
        if self._interval and self._last_call is not None:
            wait = self._last_call + self._interval - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def embed(self, texts: Sequence[str], input_type: InputType) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = list(texts[start : start + BATCH_SIZE])
            self._pace()
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
