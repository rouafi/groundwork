import math

import pytest
from pydantic import ValidationError

from groundwork.core.domain.search import Chunk, SearchHit


def _chunk(**fields: object) -> Chunk:
    return Chunk.model_validate(
        {
            "id": "acme-i-1-c-001",
            "doc_id": "acme-i-1",
            "role": "head of sales",
            "text": "Body.",
            **fields,
        }
    )


def test_a_chunk_is_indexed_as_its_context_then_its_text() -> None:
    assert _chunk(context="From the sales interview.").indexed_text == (
        "From the sales interview.\n\nBody."
    )


def test_a_chunk_without_context_is_indexed_as_its_text() -> None:
    assert _chunk().indexed_text == "Body."


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_an_embedding_must_be_finite(bad: float) -> None:
    with pytest.raises(ValidationError, match="finite"):
        _chunk(embedding=(0.1, bad))


def test_chunks_and_hits_are_frozen_and_reject_unknown_fields() -> None:
    chunk = _chunk()
    with pytest.raises(ValidationError):
        chunk.text = "other"
    with pytest.raises(ValidationError):
        Chunk.model_validate({**chunk.model_dump(), "extra": 1})
    with pytest.raises(ValidationError):
        SearchHit(chunk_id="c", doc_id="d", text="", score=1.0)
