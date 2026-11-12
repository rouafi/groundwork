"""ModelPort: single-shot model calls for the workflows of the core.

The core asks for a capability tier, never for a model id: adapters map tiers to
models. Untrusted text (an interview, an email) always travels as `document`, a
separate block that prompts present as data, never as instructions.

Contract (tests/contracts/test_model_contract.py, run against every adapter):
- `complete_structured` returns an instance of `schema`.
- `cite` returns statements whose quotes are verbatim spans of `document`:
  `document[quote.start:quote.end] == quote.text`.
- Every answer reports the tokens it cost.
- The same inputs give the same answer (replay is keyed on inputs).
"""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from groundwork.core.domain.knowhow import Usage

Tier = Literal["extraction", "cheap"]


class _Answer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Quote(_Answer):
    """A verbatim span of the document, 0-based, end exclusive."""

    text: str
    start: int
    end: int


class CitedStatement(_Answer):
    """A statement the model wrote, with the document spans that support it."""

    text: str
    quotes: tuple[Quote, ...]


class Answer[T](_Answer):
    """A model answer and what it cost."""

    value: T
    usage: Usage


class ModelPort(Protocol):
    """What the core may ask a language model."""

    def complete_structured[S: BaseModel](
        self, *, tier: Tier, system: str, user: str, schema: type[S], document: str | None = None
    ) -> Answer[S]:
        """Return an answer validated against `schema`."""

    def complete_text(
        self, *, tier: Tier, system: str, user: str, document: str | None = None
    ) -> Answer[str]:
        """Return free text."""

    def cite(
        self, *, tier: Tier, system: str, instruction: str, document: str
    ) -> Answer[tuple[CitedStatement, ...]]:
        """Return statements about `document`, each grounded in verbatim spans of it."""
