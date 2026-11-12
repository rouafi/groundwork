from pathlib import Path

import pytest

from groundwork.core.domain.errors import PackError
from groundwork.core.domain.knowhow import Interview
from groundwork.core.domain.search import Chunk, RetrievalQuestion
from groundwork.core.services.chunking import chunk_interview
from groundwork.core.services.indexing import chunk_problems, dump_chunks, question_problems
from groundwork.core.services.packs import (
    CHUNKS_FILE,
    load_chunks,
    load_interviews,
    load_retrieval_questions,
)

INTERVIEWS = {
    "acme-i-1": Interview(
        id="acme-i-1",
        role="head of sales",
        text="Interviewer: Prices?\n\nHead of sales: We quote the catalog price exactly.",
    )
}


def _chunk(**fields: object) -> Chunk:
    data = {
        "id": "acme-i-1-c-001",
        "doc_id": "acme-i-1",
        "role": "head of sales",
        "text": "We quote the catalog price exactly.",
        "context": "About pricing.",
        "embedding": (0.5, -0.5),
        **fields,
    }
    return Chunk.model_validate(data)


def test_a_valid_index_has_no_problem() -> None:
    assert chunk_problems([_chunk()], INTERVIEWS) == []


def test_line_breaks_do_not_matter_when_matching_the_interview() -> None:
    chunk = _chunk(
        text="Interviewer: Prices?\n\nHead of sales: We quote   the catalog price exactly."
    )
    assert chunk_problems([chunk], INTERVIEWS) == []


def test_a_chunk_from_an_unknown_interview_is_a_problem() -> None:
    (problem,) = chunk_problems([_chunk(doc_id="acme-i-9")], INTERVIEWS)
    assert "acme-i-1-c-001" in problem
    assert "unknown interview 'acme-i-9'" in problem


def test_a_chunk_whose_text_is_not_in_its_interview_is_a_problem() -> None:
    # What a CRM fact would look like if it reached the index (ADR 0002).
    fact = "Insight Pro: Dashboards, alerts and API access for up to 50 users. 1490.00 EUR."
    (problem,) = chunk_problems([_chunk(text=fact)], INTERVIEWS)
    assert "text is not in interview acme-i-1" in problem


def test_duplicate_ids_missing_embeddings_and_mixed_sizes_are_problems() -> None:
    problems = chunk_problems(
        [_chunk(), _chunk(), _chunk(id="acme-i-1-c-002", embedding=())], INTERVIEWS
    )
    assert any("duplicate id" in p for p in problems)
    assert any("c-002: no embedding" in p for p in problems)
    assert any("different sizes" in p for p in problems)


def test_the_dump_is_one_sorted_line_per_chunk_and_idempotent() -> None:
    chunks = [_chunk(), _chunk(id="acme-i-1-c-002")]
    dumped = dump_chunks(chunks)
    lines = dumped.splitlines()
    assert len(lines) == 2 and dumped.endswith("\n")
    assert lines[0].startswith('{"context"')
    assert dump_chunks(chunks) == dumped


def test_a_dumped_index_loads_back_unchanged(tmp_path: Path) -> None:
    chunks = (_chunk(), _chunk(id="acme-i-1-c-002", context="About tone."))
    path = tmp_path / CHUNKS_FILE
    path.parent.mkdir()
    path.write_text(dump_chunks(chunks), encoding="utf-8")
    assert load_chunks(tmp_path) == chunks


def test_a_pack_that_was_never_indexed_has_no_chunks(tmp_path: Path) -> None:
    assert load_chunks(tmp_path) == ()


def test_a_bad_line_names_the_file_and_the_line(tmp_path: Path) -> None:
    path = tmp_path / CHUNKS_FILE
    path.parent.mkdir()
    path.write_text(dump_chunks([_chunk()]) + '{"id": "x"}\n', encoding="utf-8")
    with pytest.raises(PackError, match=r"chunks\.jsonl:2"):
        load_chunks(tmp_path)


def _question(**fields: object) -> RetrievalQuestion:
    data = {
        "question": "How do we quote prices?",
        "expected_doc_id": "acme-i-1",
        "expected_quote": "We quote the catalog price exactly.",
        **fields,
    }
    return RetrievalQuestion.model_validate(data)


def test_a_question_whose_quote_is_in_its_interview_is_fine() -> None:
    assert question_problems([_question()], INTERVIEWS) == []


def test_a_question_names_its_number_when_the_interview_is_unknown() -> None:
    (problem,) = question_problems([_question(), _question(expected_doc_id="acme-i-9")], INTERVIEWS)
    assert problem == "retrieval question 2: unknown interview 'acme-i-9'"


def test_a_question_whose_quote_is_not_in_the_interview_is_a_problem() -> None:
    (problem,) = question_problems([_question(expected_quote="We never quote.")], INTERVIEWS)
    assert problem == "retrieval question 1: expected quote is not in interview acme-i-1"


PACKS = Path(__file__).resolve().parents[2] / "client_packs"


@pytest.mark.parametrize("pack", ["acme", "beta"])
def test_the_shipped_questions_are_ten_and_each_quote_is_in_exactly_one_chunk(pack: str) -> None:
    interviews = {i.id: i for i in load_interviews(PACKS / pack)}
    questions = load_retrieval_questions(PACKS / pack)
    assert len(questions) == 10
    assert question_problems(questions, interviews) == []
    for item in questions:
        chunks = chunk_interview(interviews[item.expected_doc_id])
        holding = [
            c.id
            for c in chunks
            if " ".join(item.expected_quote.split()) in " ".join(c.text.split())
        ]
        assert len(holding) == 1, (item.question, holding)
