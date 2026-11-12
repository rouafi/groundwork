from pathlib import Path

import pytest

from groundwork.core.domain.errors import ModelError
from groundwork.core.domain.knowhow import Interview
from groundwork.core.services.chunking import chunk_interview
from groundwork.core.services.indexing import build_index, contextualize
from groundwork.core.services.packs import load_interviews
from tests.fakes import CALL_USAGE, HashEmbedding, StubModel

PACKS = Path(__file__).resolve().parents[2] / "client_packs"
INTERVIEW = Interview(
    id="acme-i-1",
    role="head of sales",
    text="Interviewer: Prices?\n\nHead of sales: We quote the catalog price exactly.",
)


def _model(context: str = "The head of sales on pricing.") -> StubModel:
    return StubModel(text=lambda **_: context)


def test_the_whole_interview_is_the_document_and_the_chunk_is_in_the_request() -> None:
    (chunk,) = chunk_interview(INTERVIEW)
    model = _model()
    contextualize(chunk, INTERVIEW, model, "system prompt")
    ((method, call),) = model.calls
    assert method == "complete_text"
    assert call["tier"] == "cheap"
    assert call["document"] == INTERVIEW.text
    assert call["system"] == "system prompt"
    assert chunk.text in call["user"]


def test_the_context_is_stored_trimmed_and_costs_one_call() -> None:
    (chunk,) = chunk_interview(INTERVIEW)
    done, usage = contextualize(chunk, INTERVIEW, _model("  About pricing.\n"), "s")
    assert done.context == "About pricing."
    assert done.text == chunk.text
    assert usage == CALL_USAGE


def test_an_empty_context_is_an_error() -> None:
    (chunk,) = chunk_interview(INTERVIEW)
    with pytest.raises(ModelError, match=chunk.id):
        contextualize(chunk, INTERVIEW, _model("  "), "s")


def test_the_index_embeds_context_and_chunk_together_as_documents() -> None:
    embedding = HashEmbedding()
    chunks, usage = build_index([INTERVIEW], _model("About pricing."), embedding, "s")
    (chunk,) = chunks
    assert embedding.calls == [((chunk.indexed_text,), "document")]
    assert chunk.indexed_text.startswith("About pricing.")
    assert len(chunk.embedding) == 8
    assert usage == CALL_USAGE


def test_every_chunk_of_the_committed_interviews_is_indexed_in_order() -> None:
    interviews = load_interviews(PACKS / "acme")
    chunks, usage = build_index(interviews, _model(), HashEmbedding(), "s")
    assert [c.id for c in chunks] == [c.id for i in interviews for c in chunk_interview(i)]
    assert all(c.context and c.embedding for c in chunks)
    assert usage.input_tokens == CALL_USAGE.input_tokens * len(chunks)
