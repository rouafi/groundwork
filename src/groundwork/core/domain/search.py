"""Searchable know-how: chunks of interview text and the hits a search returns.

Only expert know-how is chunked. Facts stay in the ontology and are never embedded
(ADR 0002). Chunk text is untrusted data, never instructions.
"""

import math
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from groundwork.core.domain.facts import Id

Text = Annotated[str, Field(min_length=1)]


class _Search(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Chunk(_Search):
    """A span of one interview, with the context that situates it and its embedding.

    `context` is written by a model (Contextual Retrieval) and `embedding` by an
    embedding model; both are empty until the chunk is indexed. The index covers
    `indexed_text`, while a hit shows only `text`.
    """

    id: Id
    doc_id: Id
    role: Text
    text: Text
    context: str = ""
    embedding: tuple[float, ...] = ()

    @field_validator("embedding")
    @classmethod
    def _finite(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not all(math.isfinite(x) for x in value):
            raise ValueError("embedding values must be finite")
        return value

    @property
    def indexed_text(self) -> str:
        """What is embedded and keyword-indexed: the context, then the chunk."""
        return f"{self.context}\n\n{self.text}" if self.context else self.text


class SearchHit(_Search):
    """One ranked result. `score` is comparable only within the search that made it."""

    chunk_id: Id
    doc_id: Id
    text: Text
    score: float


class RetrievalQuestion(_Search):
    """A question a pack's index must answer: the interview and the passage it should find.

    `expected_quote` is verbatim in `expected_doc_id`, so a retrieval eval can check a hit
    by text, whatever the chunk boundaries are.
    """

    question: Text
    expected_doc_id: Id
    expected_quote: Text
