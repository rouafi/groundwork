"""The trace of one harmonization run: one JSON object per line, in this order.

`request`, `context_pack`, `step` (one per tool call), `output`, `claim_check` (one per
claim), `decision`; an aborted run ends with `error` instead. No timestamps, sorted keys:
the same run gives the same bytes, so a diff shows only what changed. Traces hold synthetic
data and are safe to publish (docs/security.md).
"""

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from groundwork.core.domain.claims import ClaimCheck
from groundwork.core.domain.harmonize import (
    AgentResult,
    AgentStep,
    ContextPack,
    Decision,
    HarmonizeRequest,
)

TraceEvent = dict[str, Any]


def system_digest(system: str) -> str:
    """sha256 of the agent's system prompt: editing the prompt invalidates a recorded trace."""
    return hashlib.sha256(system.encode("utf-8")).hexdigest()


def request_event(request: HarmonizeRequest, system: str) -> TraceEvent:
    asked = request.model_dump(mode="json", exclude={"case_id"})
    return {
        "type": "request",
        "case_id": request.id,
        "request": asked,
        "system_sha256": system_digest(system),
    }


def context_event(context: ContextPack) -> TraceEvent:
    return {"type": "context_pack", "context_pack": context.model_dump(mode="json")}


def step_events(steps: Iterable[AgentStep]) -> list[TraceEvent]:
    return [
        {"type": "step", "index": index, **step.model_dump(mode="json")}
        for index, step in enumerate(steps, start=1)
    ]


def output_event(result: AgentResult) -> TraceEvent:
    return {
        "type": "output",
        "email": result.email.model_dump(mode="json"),
        "usage": result.usage.model_dump(mode="json"),
    }


def claim_events(checks: Iterable[ClaimCheck]) -> list[TraceEvent]:
    return [{"type": "claim_check", **check.model_dump(mode="json")} for check in checks]


def decision_event(decision: Decision) -> TraceEvent:
    return {"type": "decision", **decision.model_dump(mode="json")}


def error_event(message: str) -> TraceEvent:
    return {"type": "error", "message": message}


def dump_trace(events: Iterable[TraceEvent]) -> str:
    """The text of a trace file: one sorted-key JSON object per line."""
    lines = (json.dumps(e, sort_keys=True, ensure_ascii=False) for e in events)
    return "".join(f"{line}\n" for line in lines)


def parse_trace(text: str) -> list[TraceEvent]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]
