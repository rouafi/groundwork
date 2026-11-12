"""AgentPort: draft the email of one request from a context pack, with read-only tools.

The agent only reads. It cannot send, queue or write anything: routing and sending are
done by the policy engine and the services, outside its control (ADR 0004). The request
draft, the CRM fields and the passages in the context are untrusted data, never
instructions.

Contract:
- The result's email is valid against `HarmonizedEmail`; anything else is an `AgentError`.
- Going past `limits.max_steps`, `limits.max_tokens` or `limits.timeout_s` raises
  `AgentLimitError` naming the limit; no partial email is returned.
- Every tool call appears in `steps`, in order, and the cost in `usage`.
- No tool it can call writes anything.
"""

from typing import Protocol

from groundwork.core.domain.harmonize import AgentResult, ContextPack, HarmonizeRequest
from groundwork.core.domain.policy import Limits


class AgentPort(Protocol):
    """What the harness may ask an agent."""

    def run(
        self, *, system: str, context: ContextPack, request: HarmonizeRequest, limits: Limits
    ) -> AgentResult:
        """Return the harmonized email of `request`, with the steps that led to it."""
