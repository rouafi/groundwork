from pathlib import Path

import pytest

from groundwork.core.domain.knowhow import Interview
from groundwork.core.services.chunking import (
    MAX_WORDS,
    TARGET_WORDS,
    chunk_interview,
    word_count,
)
from groundwork.core.services.packs import load_interviews

PACKS = Path(__file__).resolve().parents[2] / "client_packs"


def _words(n: int, tag: str = "w") -> str:
    return " ".join(f"{tag}{i}" for i in range(n))


def _interview(*paragraphs: str, id: str = "acme-i-9") -> Interview:
    return Interview(id=id, role="head of sales", text="\n\n".join(paragraphs))


def test_chunking_is_deterministic() -> None:
    interview = _interview(*(_words(70, f"p{i}") for i in range(12)))
    assert chunk_interview(interview) == chunk_interview(interview)


def test_ids_follow_the_document_and_carry_its_role() -> None:
    chunks = chunk_interview(_interview(_words(150, "a"), _words(150, "b"), _words(150, "c")))
    assert [c.id for c in chunks] == ["acme-i-9-c-001", "acme-i-9-c-002"]
    assert {(c.doc_id, c.role) for c in chunks} == {("acme-i-9", "head of sales")}


def test_a_chunk_closes_once_it_reaches_the_target() -> None:
    chunks = chunk_interview(_interview(_words(120, "a"), _words(100, "b"), _words(100, "c")))
    assert [word_count(c.text) for c in chunks] == [220, 100]


def test_a_chunk_never_exceeds_the_maximum_by_packing_paragraphs() -> None:
    chunks = chunk_interview(_interview(_words(190, "a"), _words(250, "b")))
    assert [word_count(c.text) for c in chunks] == [190, 250]


def test_a_long_paragraph_is_cut_at_sentence_ends() -> None:
    sentence = _words(99, "s") + "."
    chunks = chunk_interview(_interview(" ".join([sentence] * 7)))
    assert all(word_count(c.text) <= MAX_WORDS for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)
    assert sum(word_count(c.text) for c in chunks) == 7 * 99


def test_a_sentence_longer_than_the_maximum_is_cut_between_words() -> None:
    chunks = chunk_interview(_interview(_words(MAX_WORDS * 2 + 10)))
    assert [word_count(c.text) for c in chunks] == [MAX_WORDS, MAX_WORDS, 10]


def test_a_very_short_tail_joins_the_previous_chunk() -> None:
    chunks = chunk_interview(_interview(_words(210, "a"), _words(20, "b")))
    assert len(chunks) == 1
    assert word_count(chunks[0].text) == 230


def test_a_short_tail_stays_apart_when_the_merge_would_not_fit() -> None:
    chunks = chunk_interview(_interview(_words(290, "a"), _words(20, "b")))
    assert [word_count(c.text) for c in chunks] == [290, 20]


def test_blank_text_gives_no_chunk() -> None:
    assert chunk_interview(Interview(id="x-i-1", role="r", text="  \n\n  \n")) == ()


@pytest.mark.parametrize("pack", ["acme", "beta"])
def test_the_committed_interviews_are_chunked_without_losing_a_word(pack: str) -> None:
    for interview in load_interviews(PACKS / pack):
        chunks = chunk_interview(interview)
        assert chunks
        assert all(word_count(c.text) <= MAX_WORDS for c in chunks)
        assert "\n\n".join(c.text for c in chunks).split() == interview.text.split()
        assert all(c.text in interview.text for c in chunks)
    assert TARGET_WORDS < MAX_WORDS
