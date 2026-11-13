"""Evals: golden cases a pack must pass, and the thresholds that decide go-live.

A golden case is a request with what a good result looks like. It says nothing about
how the agent should write: the scorers measure the harmonized email, the claims and
the route, and the thresholds turn those measures into a verdict (docs/evals.md).
"""

import re
from typing import Annotated, Literal

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


class FactScore(_Eval):
    """Fact accuracy of one email: false claims, and `must_contain` strings it lacks."""

    false_claims: int = Field(ge=0)
    missing: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.false_claims == 0 and not self.missing


class TraceabilityScore(_Eval):
    """Whether what an email cites exists: unknown node ids, and cited rules that do not apply."""

    cited: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    inapplicable: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.unknown and not self.inapplicable


class RetrievalScore(_Eval):
    """recall@k over a pack's retrieval questions: how many found their passage."""

    k: int = Field(ge=1)
    found: int = Field(ge=0)
    total: int = Field(ge=0)
    missed: tuple[str, ...] = ()

    @property
    def recall(self) -> float:
        return self.found / self.total if self.total else 0.0


Tone = Annotated[int, Field(ge=1, le=5)]


class CalibrationCase(_Eval):
    """An email a human scored for tone, from 1 to 5. The labels are the human's alone."""

    id: CaseId
    subject: Text
    body: Text
    human_tone: Tone


class RuleVerdict(_Eval):
    """The judge's verdict on one rule the email had to follow."""

    rule_id: Text
    verdict: Literal["complied", "violated", "not_applicable"]
    reason: str


class JudgeVerdict(_Eval):
    """What the judge returns for one email: a tone score, and a verdict per rule."""

    tone: Tone
    tone_reason: str
    rules: tuple[RuleVerdict, ...] = ()

    @property
    def violations(self) -> tuple[str, ...]:
        return tuple(r.rule_id for r in self.rules if r.verdict == "violated")


class Agreement(_Eval):
    """How often the judge lands within one point of the human label."""

    agree: int = Field(ge=0)
    total: int = Field(ge=0)
    differences: tuple[int, ...] = ()

    @property
    def rate(self) -> float:
        return self.agree / self.total if self.total else 0.0


class RawResult(_Eval):
    """What the raw draft scores through the same scorers: the 'before' of before and after."""

    route: Route
    false_claims: int = Field(ge=0)
    forbidden_hits: tuple[str, ...] = ()
    tone: Tone
    rule_violations: tuple[str, ...] = ()


class CaseResult(_Eval):
    """Everything measured for one golden case, harmonized and raw."""

    id: CaseId
    tags: tuple[str, ...] = ()
    channel: MessageChannel
    expected_route: Route
    route: Route
    facts: FactScore
    forbidden_hits: tuple[str, ...] = ()
    traceability: TraceabilityScore
    tone: Tone
    tone_reason: str
    rule_violations: tuple[str, ...] = ()
    raw: RawResult

    @property
    def routing_ok(self) -> bool:
        return self.route == self.expected_route


class PackMetrics(_Eval):
    """The numbers of a pack, after and before the agent. `None` means not measured."""

    cases: int = Field(ge=0)
    fact_false_claims: int = Field(ge=0)
    rule_violations: int = Field(ge=0)
    tone_mean: float
    routing_accuracy: Fraction
    traceability: Fraction
    retrieval_recall_at_5: Fraction | None = None
    judge_agreement: Fraction
    raw_false_claims: int = Field(ge=0)
    raw_forbidden_hits: int = Field(ge=0)
    raw_tone_mean: float


class ThresholdResult(_Eval):
    """One scorer against its threshold, with a message that names the scorer."""

    scorer: Text
    value: float | None
    threshold: float
    passed: bool
    message: str


class PackResult(_Eval):
    """The outcome of the evals of one pack."""

    pack: Text
    cases: tuple[CaseResult, ...]
    metrics: PackMetrics
    thresholds: tuple[ThresholdResult, ...]
    retrieval: RetrievalScore | None = None
    agreement: Agreement
    notes: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return all(t.passed for t in self.thresholds)
