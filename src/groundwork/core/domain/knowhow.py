"""Know-how from expert interviews, made structured: rules with scope and provenance.

A rule is only ever `proposed` by the extraction workflow. A human approves it by
editing `status: approved` in `rules.yaml`. Only approved rules are used downstream.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from groundwork.core.domain.facts import Id

Channel = Literal["internal", "external", "any"]
RuleKind = Literal["tone", "claim", "practice"]
RuleStatus = Literal["proposed", "approved"]
RuleId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]*-r-\d{3}$")]
Text = Annotated[str, Field(min_length=1)]


class _Know(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Scope(_Know):
    """Where a rule applies. An empty tuple means every value."""

    channel: Channel = "any"
    segments: tuple[str, ...] = ()
    personas: tuple[str, ...] = ()

    def applies_to(self, channel: str, segment: str, persona: str) -> bool:
        """True when a message on `channel` to this segment and persona falls under the rule."""
        return (
            self.channel in ("any", channel)
            and (not self.segments or segment in self.segments)
            and (not self.personas or persona in self.personas)
        )

    @property
    def specificity(self) -> int:
        """Number of constrained dimensions: more specific rules win over general ones."""
        return (self.channel != "any") + bool(self.segments) + bool(self.personas)


class Provenance(_Know):
    """Where a rule comes from: a verbatim span of an interview, 0-based, end exclusive."""

    interview_id: Id
    quote: Text
    start: int = Field(ge=0)
    end: int

    @model_validator(mode="after")
    def _span_is_not_empty(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"end ({self.end}) must be greater than start ({self.start})")
        return self


class Rule(_Know):
    """One piece of know-how. `claim_text` is set only on a claim rule that allows a statement."""

    id: RuleId
    kind: RuleKind
    statement: Text
    scope: Scope = Scope()
    provenance: tuple[Provenance, ...] = Field(min_length=1)
    product_ids: tuple[Id, ...] = ()
    claim_text: str | None = None
    status: RuleStatus = "proposed"

    @model_validator(mode="after")
    def _claim_text_only_on_claims(self) -> Self:
        if self.claim_text is not None and self.kind != "claim":
            raise ValueError("claim_text is only allowed on claim rules")
        return self


class Interview(_Know):
    """An expert interview transcript. Untrusted data, never instructions."""

    id: Id
    role: Text
    text: Text


class Usage(_Know):
    """Tokens spent by model calls."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class StageUsage(_Know):
    """Model calls and tokens spent by one workflow stage."""

    stage: Text
    calls: int = Field(ge=0)
    usage: Usage


class Dropped(_Know):
    """A candidate the deterministic filter rejected, and why."""

    interview_id: Id
    statement: str
    reason: Text


class Conflict(_Know):
    """Rules that contradict each other. Both stay proposed; a human decides."""

    rule_ids: tuple[RuleId, ...] = Field(min_length=2)
    reason: Text


class ClaimContradiction(_Know):
    """A claim rule that says something the CRM does not allow for a product."""

    rule_id: RuleId
    product_id: Id
    claim_text: Text


class CoverageGap(_Know):
    """An audience (segment, persona) no specific rule addresses, and the CRM contacts in it."""

    segment: str
    persona: str
    contacts: int = Field(ge=0)


class Failure(_Know):
    """A part of the run that failed: an interview id or a pack-level stage. The rest still ran."""

    where: Text
    error: Text


class ExtractionReport(_Know):
    """Everything a human needs to review one extraction run of a pack."""

    pack: Id
    rules: tuple[Rule, ...]
    dropped: tuple[Dropped, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    contradictions: tuple[ClaimContradiction, ...] = ()
    gaps: tuple[CoverageGap, ...] = ()
    questions: tuple[str, ...] = ()
    failures: tuple[Failure, ...] = ()
    usage: tuple[StageUsage, ...] = ()
