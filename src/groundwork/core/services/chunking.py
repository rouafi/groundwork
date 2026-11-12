"""Cut an interview into chunks, deterministically.

Paragraphs are the unit (an interview paragraph is one turn of the conversation).
Paragraphs are packed until a chunk reaches `TARGET_WORDS`, and never beyond
`MAX_WORDS`. A paragraph longer than `MAX_WORDS` is cut at sentence ends, and as a
last resort between words. The same interview always gives the same ids and the
same boundaries.
"""

import re

from groundwork.core.domain.knowhow import Interview
from groundwork.core.domain.search import Chunk

TARGET_WORDS = 200
MAX_WORDS = 300
MIN_TAIL_WORDS = 60

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def chunk_interview(interview: Interview) -> tuple[Chunk, ...]:
    """Return the chunks of one interview, ids `<interview id>-c-001`, `-c-002`, ..."""
    pieces = [piece for p in _paragraphs(interview.text) for piece in _fit(p)]
    texts = _pack(pieces)
    return tuple(
        Chunk(id=f"{interview.id}-c-{n:03d}", doc_id=interview.id, role=interview.role, text=text)
        for n, text in enumerate(texts, start=1)
    )


def word_count(text: str) -> int:
    return len(text.split())


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in _PARAGRAPH_BREAK.split(text) if p.strip()]


def _fit(paragraph: str) -> list[str]:
    """Return the paragraph whole, or cut so that every piece is within `MAX_WORDS`."""
    if word_count(paragraph) <= MAX_WORDS:
        return [paragraph]
    pieces: list[str] = []
    current: list[str] = []
    for sentence in _SENTENCE_END.split(paragraph):
        for part in _split_words(sentence):
            if current and word_count(" ".join([*current, part])) > MAX_WORDS:
                pieces.append(" ".join(current))
                current = []
            current.append(part)
    pieces.append(" ".join(current))
    return pieces


def _split_words(sentence: str) -> list[str]:
    words = sentence.split()
    if len(words) <= MAX_WORDS:
        return [sentence]
    return [" ".join(words[i : i + MAX_WORDS]) for i in range(0, len(words), MAX_WORDS)]


def _pack(pieces: list[str]) -> list[str]:
    chunks: list[list[str]] = []
    current: list[str] = []
    words = 0
    for piece in pieces:
        size = word_count(piece)
        if current and words + size > MAX_WORDS:
            chunks.append(current)
            current, words = [], 0
        current.append(piece)
        words += size
        if words >= TARGET_WORDS:
            chunks.append(current)
            current, words = [], 0
    if current:
        chunks.append(current)
    return _merge_tail(["\n\n".join(c) for c in chunks])


def _merge_tail(texts: list[str]) -> list[str]:
    """Fold a very short last chunk into the one before it when the result still fits."""
    if len(texts) >= 2 and word_count(texts[-1]) < MIN_TAIL_WORDS:
        merged = f"{texts[-2]}\n\n{texts[-1]}"
        if word_count(merged) <= MAX_WORDS:
            return [*texts[:-2], merged]
    return texts
