"""Golden data for rule extraction: what a good run of a pack must and must not produce.

Written by humans with the experts. Quotes are verbatim spans of the interviews, so
expected items are matched to extracted rules by where they come from, not by wording.
Semantic scoring of statements needs the calibrated judge of PRD-006.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from groundwork.core.domain.facts import Id
from groundwork.core.domain.knowhow import Channel, RuleKind

Quote = Annotated[str, Field(min_length=1)]


class _Golden(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExpectedRule(_Golden):
    kind: RuleKind
    statement: str = Field(min_length=1)
    channel: Channel = "any"
    segments: tuple[str, ...] = ()
    personas: tuple[str, ...] = ()
    quote: Quote


class GoldenInterview(_Golden):
    interview_id: Id
    expected_rules: tuple[ExpectedRule, ...] = Field(min_length=1)
    must_not_extract: tuple[Quote, ...] = ()


class ExpectedConflict(_Golden):
    """Two quotes, from different rules, that the run must flag as conflicting."""

    quotes: tuple[tuple[Id, Quote], tuple[Id, Quote]]
    reason: str = Field(min_length=1)


class ExpectedContradiction(_Golden):
    """A claim the run must flag as outside a product's allowed claims."""

    interview_id: Id
    product_id: Id
    quote: Quote


class ExtractionGolden(_Golden):
    """Schema of `client_packs/<client>/evals/extraction_golden.yaml`."""

    pack: Id
    interviews: tuple[GoldenInterview, ...] = Field(min_length=1)
    expected_conflicts: tuple[ExpectedConflict, ...] = ()
    expected_contradictions: tuple[ExpectedContradiction, ...] = ()
