"""PassthroughAgent: an AgentPort that returns the draft as the email, unchanged.

It stands for a faulty or compromised agent, or for a pipeline with no agent at all. It
exists to show, and to test, that the claim check and the policy engine catch what an
agent lets through: the harness never relies on the model behaving.
"""

from groundwork.core.domain.harmonize import (
    AgentResult,
    ContextPack,
    HarmonizedEmail,
    HarmonizeRequest,
)
from groundwork.core.domain.knowhow import Usage
from groundwork.core.domain.policy import Limits

SUBJECT = "(draft, unchanged)"
RATIONALE = "No agent ran: the draft goes through exactly as written."


class PassthroughAgent:
    def run(
        self, *, system: str, context: ContextPack, request: HarmonizeRequest, limits: Limits
    ) -> AgentResult:
        email = HarmonizedEmail(subject=SUBJECT, body=request.draft, rationale=RATIONALE)
        return AgentResult(email=email, steps=(), usage=Usage())
