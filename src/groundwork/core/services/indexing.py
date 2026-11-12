"""Build the searchable index of a pack: chunk, contextualize, embed.

Contextual Retrieval: the cheap model reads the whole interview and the chunk and
writes one or two sentences that situate the chunk. The context and the chunk are
embedded and keyword-indexed together, so a chunk that says "that plan" is found by
the name of the plan. Interviews are untrusted data and travel as `document`.
"""

from collections.abc import Sequence

from groundwork.core.domain.errors import ModelError
from groundwork.core.domain.knowhow import Interview, Usage
from groundwork.core.domain.search import Chunk
from groundwork.core.ports.embedding import EmbeddingPort
from groundwork.core.ports.model import ModelPort
from groundwork.core.services.chunking import chunk_interview


def contextualize(
    chunk: Chunk, interview: Interview, model: ModelPort, system: str
) -> tuple[Chunk, Usage]:
    """Return the chunk with its context, and what the call cost."""
    answer = model.complete_text(
        tier="cheap",
        system=system,
        user=f"Chunk:\n{chunk.text}\n\nWrite the context for this chunk.",
        document=interview.text,
    )
    context = answer.value.strip()
    if not context:
        raise ModelError(f"the model wrote no context for chunk {chunk.id}")
    return chunk.model_copy(update={"context": context}), answer.usage


def build_index(
    interviews: Sequence[Interview], model: ModelPort, embedding: EmbeddingPort, system: str
) -> tuple[tuple[Chunk, ...], Usage]:
    """Chunk every interview, contextualize each chunk, embed context and chunk together."""
    usage = Usage()
    contextualized: list[Chunk] = []
    for interview in interviews:
        for chunk in chunk_interview(interview):
            done, cost = contextualize(chunk, interview, model, system)
            contextualized.append(done)
            usage = usage + cost
    vectors = embedding.embed([c.indexed_text for c in contextualized], "document")
    chunks = tuple(
        c.model_copy(update={"embedding": tuple(v)})
        for c, v in zip(contextualized, vectors, strict=True)
    )
    return chunks, usage
