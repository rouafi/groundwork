"""Build the searchable index of a pack: chunk, contextualize, embed.

Contextual Retrieval: the cheap model reads the whole interview and the chunk and
writes one or two sentences that situate the chunk. The context and the chunk are
embedded and keyword-indexed together, so a chunk that says "that plan" is found by
the name of the plan. Interviews are untrusted data and travel as `document`.
"""

import json
from collections.abc import Sequence

from groundwork.core.domain.errors import ModelError
from groundwork.core.domain.knowhow import Interview, Usage
from groundwork.core.domain.search import Chunk, RetrievalQuestion
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


def dump_chunks(chunks: Sequence[Chunk]) -> str:
    """The text of `chunks.jsonl`: one chunk per line, keys sorted, so a diff stays small."""
    lines = (
        json.dumps(c.model_dump(mode="json"), sort_keys=True, ensure_ascii=False) for c in chunks
    )
    return "".join(f"{line}\n" for line in lines)


def chunk_problems(chunks: Sequence[Chunk], interviews: dict[str, Interview]) -> list[str]:
    """Every way an index can disagree with the interviews it claims to come from.

    Only interviews are indexed: a chunk must be a verbatim span of a known interview,
    so no CRM fact can reach the index (ADR 0002).
    """
    problems: list[str] = []
    sizes = {len(c.embedding) for c in chunks}
    if len(sizes) > 1:
        problems.append(f"index: embeddings of different sizes {sorted(sizes)}")
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.id in seen:
            problems.append(f"chunk {chunk.id}: duplicate id")
        seen.add(chunk.id)
        if not chunk.embedding:
            problems.append(f"chunk {chunk.id}: no embedding")
        interview = interviews.get(chunk.doc_id)
        if interview is None:
            problems.append(f"chunk {chunk.id}: unknown interview {chunk.doc_id!r}")
        elif " ".join(chunk.text.split()) not in " ".join(interview.text.split()):
            problems.append(f"chunk {chunk.id}: text is not in interview {chunk.doc_id}")
    if chunks:
        indexed = {c.doc_id for c in chunks}
        problems += [
            f"index: interview {i} has no chunk, run `groundwork index`"
            for i in sorted(interviews)
            if i not in indexed
        ]
    return problems


def question_problems(
    questions: Sequence[RetrievalQuestion], interviews: dict[str, Interview]
) -> list[str]:
    """Every retrieval question whose expected passage is not really in its interview."""
    problems: list[str] = []
    for number, item in enumerate(questions, start=1):
        where = f"retrieval question {number}"
        interview = interviews.get(item.expected_doc_id)
        if interview is None:
            problems.append(f"{where}: unknown interview {item.expected_doc_id!r}")
        elif " ".join(item.expected_quote.split()) not in " ".join(interview.text.split()):
            problems.append(f"{where}: expected quote is not in interview {item.expected_doc_id}")
    return problems
