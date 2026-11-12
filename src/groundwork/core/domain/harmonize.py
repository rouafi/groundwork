"""Types of the harmonization flow: request, context, the agent's email, the decision.

The model drafts an email; code decides what happens to it (ADR 0004). Everything
here is plain data: a trace is these types, one event per line.
"""

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from groundwork.core.domain.facts import ContactContext, Id
from groundwork.core.domain.knowhow import Rule, Usage
from groundwork.core.domain.search import SearchHit

MessageChannel = Literal["internal", "external"]
Route = Literal["auto_send", "approval", "blocked"]
Text = Annotated[str, Field(min_length=1)]
CASE_ID_LENGTH = 12


class _Harmonize(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HarmonizeRequest(_Harmonize):
    """Rewrite `draft`, addressed to one contact, for a channel. The draft is untrusted data."""

    contact_id: Id
    channel: MessageChannel
    draft: Text
    case_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")] | None = None

    @property
    def id(self) -> str:
        """The given case id, or the first 12 hex characters of the request hash."""
        return self.case_id or request_hash(self)[:CASE_ID_LENGTH]


def request_hash(request: HarmonizeRequest) -> str:
    """sha256 of the canonical JSON of what the request asks, whatever its case id."""
    asked = {"contact_id": request.contact_id, "channel": request.channel, "draft": request.draft}
    return hashlib.sha256(json.dumps(asked, sort_keys=True).encode("utf-8")).hexdigest()


class ContextPack(_Harmonize):
    """What the agent starts from, within a token budget. `truncated` lists what was dropped."""

    contact_context: ContactContext
    rules: tuple[Rule, ...]
    passages: tuple[SearchHit, ...]
    estimated_tokens: int = Field(ge=0)
    truncated: tuple[str, ...] = ()


class HarmonizedEmail(_Harmonize):
    """The agent's answer: the email, why, and the nodes (rules, products, passages) it used."""

    subject: Text
    body: Text
    rationale: Text
    cited_nodes: tuple[Id, ...] = ()


class AgentStep(_Harmonize):
    """One tool call of the agent, as it is traced."""

    tool: Text
    arguments: dict[str, Any]
    result_summary: str


class AgentResult(_Harmonize):
    """A finished agent run: the email, the steps that led to it, and what it cost."""

    email: HarmonizedEmail
    steps: tuple[AgentStep, ...] = ()
    usage: Usage = Usage()


class Decision(_Harmonize):
    """What happens to the email, and why. A decision always carries at least one reason."""

    route: Route
    reasons: tuple[Text, ...]

    @model_validator(mode="after")
    def _explained(self) -> "Decision":
        if not self.reasons:
            raise ValueError("a decision needs at least one reason")
        return self


ApprovalStatus = Literal["pending", "approved", "rejected"]


class ApprovalItem(_Harmonize):
    """An email waiting for a human. `id` is the case id, so a case is queued once."""

    id: Id
    contact_id: Id
    email: HarmonizedEmail
    decision: Decision
    status: ApprovalStatus = "pending"
    reason: str | None = None
