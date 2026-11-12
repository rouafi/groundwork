"""The harmonization flow: context, agent, claim check, policy, then the one side effect.

The model drafts; code decides (ADR 0004). In order:
1. assemble the context pack of the contact (facts, rules, passages) within its budget;
2. run the agent with the pack's limits: it can read, it cannot send or queue anything;
3. check the claims of the email it wrote against the CRM (`check_claims`);
4. let the policy engine decide `auto_send`, `approval` or `blocked`;
5. write the trace, then act on the decision: send, queue for a human, or nothing.

This service and `approvals` are the only code that calls `MessagingPort` and
`ApprovalPort` (an import-linter contract pins it). A run that fails, including an agent
that goes past a limit, sends and queues nothing and still leaves a trace that ends with
the error.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from groundwork.core.domain.claims import ClaimCheck
from groundwork.core.domain.errors import EmbeddingMissError, GroundworkError
from groundwork.core.domain.facts import Contact
from groundwork.core.domain.harmonize import (
    AgentStep,
    ApprovalItem,
    ContextPack,
    Decision,
    HarmonizedEmail,
    HarmonizeRequest,
)
from groundwork.core.domain.knowhow import Rule
from groundwork.core.domain.policy import Policies
from groundwork.core.domain.search import SearchHit
from groundwork.core.domain.trace import (
    TraceEvent,
    claim_events,
    context_event,
    decision_event,
    dump_trace,
    error_event,
    output_event,
    request_event,
    step_events,
)
from groundwork.core.ports.agent import AgentPort
from groundwork.core.ports.approval import ApprovalPort
from groundwork.core.ports.crm import CrmPort
from groundwork.core.ports.messaging import MessagingPort
from groundwork.core.ports.model import ModelPort
from groundwork.core.services.claims import check_claims
from groundwork.core.services.context import contact_context
from groundwork.core.services.context_pack import DEFAULT_BUDGET, build_context_pack
from groundwork.core.services.policy import decide


@dataclass(frozen=True)
class HarmonizeFlow:
    """Everything one pack's flow needs. `search` finds passages for a query, or is None."""

    crm: CrmPort
    rules: tuple[Rule, ...]
    agent: AgentPort
    model: ModelPort
    messaging: MessagingPort
    approval: ApprovalPort
    policies: Policies
    system: str
    claims_prompt: str
    traces_dir: Path
    search: Callable[[str], Sequence[SearchHit]] | None = None
    budget: int = DEFAULT_BUDGET


@dataclass(frozen=True)
class HarmonizeOutcome:
    """What a run produced. `trace_id` is the case id, the trace file's name."""

    email: HarmonizedEmail
    decision: Decision
    trace_id: str
    steps: tuple[AgentStep, ...]
    claim_checks: tuple[ClaimCheck, ...]
    context: ContextPack


def harmonize(flow: HarmonizeFlow, request: HarmonizeRequest) -> HarmonizeOutcome:
    """Run the flow for one request. Raises `NotFoundError` for an unknown contact."""
    contact = contact_context(flow.crm, request.contact_id)
    passages, note = _passages(flow, request)
    pack = build_context_pack(contact, flow.rules, passages, request.channel, flow.budget)
    if note:
        pack = pack.model_copy(update={"truncated": (*pack.truncated, note)})
    events: list[TraceEvent] = [request_event(request, flow.system), context_event(pack)]
    try:
        result = flow.agent.run(
            system=flow.system, context=pack, request=request, limits=flow.policies.limits
        )
        events += [*step_events(result.steps), output_event(result)]
        text = f"{result.email.subject}\n\n{result.email.body}"
        checks = tuple(check_claims(text, flow.crm, flow.model, flow.claims_prompt))
        events += claim_events(checks)
        decision = decide(result.email, checks, request.channel, flow.policies)
    except GroundworkError as exc:
        events.append(error_event(str(exc)))
        _write_trace(flow.traces_dir, request.id, events)
        raise
    events.append(decision_event(decision))
    _write_trace(flow.traces_dir, request.id, events)
    _act(flow, request, result.email, decision, contact.contact)
    return HarmonizeOutcome(
        email=result.email,
        decision=decision,
        trace_id=request.id,
        steps=result.steps,
        claim_checks=checks,
        context=pack,
    )


def _passages(
    flow: HarmonizeFlow, request: HarmonizeRequest
) -> tuple[tuple[SearchHit, ...], str | None]:
    """The passages for the draft. Without a recorded embedding of it (replay) there are none,
    and the pack says so: passages are an enrichment, never a reason to fail the run."""
    if flow.search is None:
        return (), None
    try:
        return tuple(flow.search(request.draft)), None
    except EmbeddingMissError:
        return (), "passages unavailable: the draft's embedding is not recorded (replay)"


def _act(
    flow: HarmonizeFlow,
    request: HarmonizeRequest,
    email: HarmonizedEmail,
    decision: Decision,
    contact: Contact,
) -> None:
    if decision.route == "auto_send":
        flow.messaging.send(email, contact)
    elif decision.route == "approval":
        flow.approval.submit(
            ApprovalItem(
                id=request.id, contact_id=request.contact_id, email=email, decision=decision
            )
        )


def _write_trace(directory: Path, case_id: str, events: list[TraceEvent]) -> None:
    """Write the trace, leaving an identical existing file untouched."""
    path = directory / f"{case_id}.jsonl"
    text = dump_trace(events)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
