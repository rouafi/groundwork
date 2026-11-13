"""ReplayAgent: AgentPort served from a recorded trace. No network, never a live fallback.

The trace of a case is `<traces_dir>/<case id>.jsonl`, written by the harmonize service.
Only the agent's own work is replayed (its steps, its email, its cost). The claim checks
and the policy are recomputed live by the caller. A trace is refused, not replayed, when
the request, the system prompt or the context pack no longer match what was recorded, or
when its steps exceed the current limits.
"""

from pathlib import Path

from groundwork.core.domain.errors import AgentLimitError, TraceMissError, TraceStaleError
from groundwork.core.domain.harmonize import (
    AgentResult,
    AgentStep,
    ContextPack,
    HarmonizedEmail,
    HarmonizeRequest,
)
from groundwork.core.domain.knowhow import Usage
from groundwork.core.domain.policy import Limits
from groundwork.core.domain.trace import TraceEvent, parse_trace, system_digest
from groundwork.core.ports.agent import AgentPort


class ReplayAgent:
    def __init__(self, traces_dir: Path) -> None:
        self._directory = traces_dir

    def run(
        self, *, system: str, context: ContextPack, request: HarmonizeRequest, limits: Limits
    ) -> AgentResult:
        case_id = request.id
        path = self._directory / f"{case_id}.jsonl"
        if not path.is_file():
            raise TraceMissError(case_id, str(path))
        events = parse_trace(path.read_text(encoding="utf-8"))
        recorded = {
            e["type"]: e for e in events if e["type"] in {"request", "context_pack", "output"}
        }
        self._check(case_id, recorded, system, context, request)
        steps = tuple(
            AgentStep(tool=e["tool"], arguments=e["arguments"], result_summary=e["result_summary"])
            for e in events
            if e["type"] == "step"
        )
        if len(steps) > limits.max_steps:
            raise AgentLimitError(
                "steps", f"{len(steps)} recorded tool calls, limit {limits.max_steps}"
            )
        output = recorded["output"]
        return AgentResult(
            email=HarmonizedEmail.model_validate(output["email"]),
            steps=steps,
            usage=Usage.model_validate(output["usage"]),
        )

    def _check(
        self,
        case_id: str,
        recorded: dict[str, TraceEvent],
        system: str,
        context: ContextPack,
        request: HarmonizeRequest,
    ) -> None:
        if "request" not in recorded or "context_pack" not in recorded or "output" not in recorded:
            raise TraceStaleError(case_id, "expected events (the run did not finish)")
        asked = request.model_dump(mode="json", exclude={"case_id"})
        if recorded["request"]["request"] != asked:
            raise TraceStaleError(case_id, "request")
        if recorded["request"]["system_sha256"] != system_digest(system):
            raise TraceStaleError(case_id, "system prompt")
        if ContextPack.model_validate(recorded["context_pack"]["context_pack"]) != context:
            raise TraceStaleError(case_id, "context (rules, facts or passages)")


class ResumingAgent:
    """Replay a case that has a valid trace, run only the others live.

    A trace that is missing, unfinished or stale (the prompt, the context or the request
    changed) is re-run live, so a resumed recording costs only what is not yet recorded.
    """

    def __init__(self, replay: AgentPort, live: AgentPort) -> None:
        self._replay = replay
        self._live = live

    def run(
        self, *, system: str, context: ContextPack, request: HarmonizeRequest, limits: Limits
    ) -> AgentResult:
        try:
            return self._replay.run(system=system, context=context, request=request, limits=limits)
        except (TraceMissError, TraceStaleError):
            return self._live.run(system=system, context=context, request=request, limits=limits)
