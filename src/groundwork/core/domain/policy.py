"""Policy configuration: what a domain or a client may add to the core's invariants.

The invariants themselves are code, not configuration: a false claim blocks, an
external email never auto-sends, an unknown claim goes to a human (ADR 0004, 0008).
These models can only add patterns, lower limits and turn internal auto-send off;
every attempt to go further (an unknown key, a limit above its ceiling) is rejected.
"""

import re
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

CORE_MAX_STEPS = 8
CORE_MAX_TOKENS = 60_000
CORE_TIMEOUT_S = 60


class _Policy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Limits(_Policy):
    """Hard limits of one agent run. The defaults are the core ceilings."""

    max_steps: int = Field(default=CORE_MAX_STEPS, ge=1, le=CORE_MAX_STEPS)
    max_tokens: int = Field(default=CORE_MAX_TOKENS, ge=1, le=CORE_MAX_TOKENS)
    timeout_s: float = Field(default=CORE_TIMEOUT_S, gt=0, le=CORE_TIMEOUT_S)

    def lowered_by(self, other: "LimitOverrides") -> Self:
        """These limits, each lowered to the override's value when it is lower."""
        return self.model_copy(
            update={
                name: min(getattr(self, name), value)
                for name, value in other.model_dump().items()
                if value is not None
            }
        )


class LimitOverrides(_Policy):
    """Limits a client may lower. Each is optional and capped by the core ceiling."""

    max_steps: int | None = Field(default=None, ge=1, le=CORE_MAX_STEPS)
    max_tokens: int | None = Field(default=None, ge=1, le=CORE_MAX_TOKENS)
    timeout_s: float | None = Field(default=None, gt=0, le=CORE_TIMEOUT_S)


class ForbiddenPatterns(_Policy):
    """Regular expressions that block an email on a channel when they match."""

    internal: tuple[str, ...] = ()
    external: tuple[str, ...] = ()

    @field_validator("internal", "external")
    @classmethod
    def _valid_regexes(cls, patterns: tuple[str, ...]) -> tuple[str, ...]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid regular expression {pattern!r}: {exc}") from exc
        return patterns


class Policies(_Policy):
    """The effective policies of a pack, after the domain defaults and client overrides."""

    forbidden_patterns: ForbiddenPatterns = ForbiddenPatterns()
    limits: Limits = Limits()
    auto_send_internal: bool = True


class PolicyOverrides(_Policy):
    """`client_packs/<client>/policies.yaml`: additions and tightenings, never relaxations."""

    forbidden_patterns: ForbiddenPatterns = ForbiddenPatterns()
    limits: LimitOverrides = LimitOverrides()
    auto_send_internal: bool | None = None
