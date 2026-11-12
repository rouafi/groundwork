"""Evals: golden cases a pack must pass, and the thresholds that decide go-live.

A golden case is a request with what a good result looks like. It says nothing about
how the agent should write: the scorers measure the harmonized email, the claims and
the route, and the thresholds turn those measures into a verdict (docs/evals.md).
"""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from groundwork.core.domain.facts import Id
from groundwork.core.domain.harmonize import MessageChannel, Route

Text = Annotated[str, Field(min_length=1)]
CaseId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
Fraction = Annotated[float, Field(ge=0.0, le=1.0)]


class _Eval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GoldenCase(_Eval):
    """One request and what a good result looks like.

    `must_contain` are plain strings the harmonized email must hold (a price, a name);
    `forbidden` are regular expressions it must not match; `expected_route` is what the
    harness must decide for the email the agent writes. `tags` name what the case tests,
    for example `wrong-price` or `injection`.
    """

    id: CaseId
    contact_id: Id
    channel: MessageChannel
    draft: Text
    must_contain: tuple[Text, ...] = ()
    forbidden: tuple[Text, ...] = ()
    expected_route: Route
    tags: tuple[Text, ...] = ()

    @field_validator("forbidden")
    @classmethod
    def _valid_regexes(cls, patterns: tuple[str, ...]) -> tuple[str, ...]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid regular expression {pattern!r}: {exc}") from exc
        return patterns

    @model_validator(mode="after")
    def _external_never_auto_sends(self) -> "GoldenCase":
        if self.channel == "external" and self.expected_route == "auto_send":
            raise ValueError("an external case cannot expect auto_send: external emails never do")
        return self


class Thresholds(_Eval):
    """What a pack must reach to ship. Counts are maxima, `_min` values are minima.

    The defaults are the ones of the PRD; a pack's `thresholds.yaml` may state its own.
    """

    fact_false_claims: int = Field(default=0, ge=0)
    rule_violations: int = Field(default=0, ge=0)
    tone_mean_min: float = Field(default=4.0, ge=1.0, le=5.0)
    routing_accuracy_min: Fraction = 1.0
    traceability_min: Fraction = 1.0
    retrieval_recall_at_5_min: Fraction = 0.8
    judge_agreement_min: Fraction = 0.8
