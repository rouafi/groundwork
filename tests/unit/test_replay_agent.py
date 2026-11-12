from pathlib import Path

import pytest

from groundwork.adapters.agent.replay import ReplayAgent
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
from groundwork.core.domain.trace import (
    context_event,
    dump_trace,
    output_event,
    request_event,
    step_events,
)

SYSTEM = "system prompt"
REQUEST = HarmonizeRequest(contact_id="acme-c-1", channel="external", draft="Pro is 990 EUR.")
RESULT = AgentResult(
    email=HarmonizedEmail(
        subject="Quote",
        body="Pro costs 1490.00 EUR.",
        rationale="Catalog.",
        cited_nodes=("acme-p-2",),
    ),
    steps=(
        AgentStep(
            tool="get_product_facts",
            arguments={"product_ids": ["acme-p-2"]},
            result_summary="1490.00",
        ),
    ),
    usage=Usage(input_tokens=900, output_tokens=120),
)


def _record(directory: Path, pack: ContextPack, **changes: object) -> Path:
    events = [
        request_event(REQUEST, SYSTEM),
        context_event(pack),
        *step_events(RESULT.steps),
        output_event(RESULT),
    ]
    path = directory / f"{REQUEST.id}.jsonl"
    path.write_text(dump_trace(events), encoding="utf-8")
    return path


def _replay(directory: Path, pack: ContextPack, **changes: object):
    args: dict[str, object] = {
        "system": SYSTEM,
        "context": pack,
        "request": REQUEST,
        "limits": Limits(),
    }
    return ReplayAgent(directory).run(**{**args, **changes})  # type: ignore[arg-type]


def test_a_recorded_run_is_replayed_to_the_same_result(tmp_path: Path, pack: ContextPack) -> None:
    _record(tmp_path, pack)
    assert _replay(tmp_path, pack) == RESULT


def test_a_case_with_no_trace_names_the_file_and_how_to_record(
    tmp_path: Path, pack: ContextPack
) -> None:
    with pytest.raises(TraceMissError) as miss:
        _replay(tmp_path, pack)
    assert f"{REQUEST.id}.jsonl" in str(miss.value)
    assert "GROUNDWORK_MODEL=claude" in str(miss.value)


def test_a_given_case_id_names_the_trace_file(tmp_path: Path, pack: ContextPack) -> None:
    named = REQUEST.model_copy(update={"case_id": "demo-1"})
    (tmp_path / "demo-1.jsonl").write_text(
        dump_trace([request_event(named, SYSTEM), context_event(pack), output_event(RESULT)]),
        encoding="utf-8",
    )
    assert _replay(tmp_path, pack, request=named).email == RESULT.email


@pytest.mark.parametrize(
    ("change", "what"),
    [
        ({"system": "an edited prompt"}, "system prompt"),
        (
            {"request": REQUEST.model_copy(update={"case_id": "x", "draft": "Another draft."})},
            "request",
        ),
    ],
)
def test_a_trace_is_refused_when_what_was_asked_changed(
    tmp_path: Path, pack: ContextPack, change: dict[str, object], what: str
) -> None:
    _record(tmp_path, pack)
    if "request" in change:
        (tmp_path / "x.jsonl").write_text((tmp_path / f"{REQUEST.id}.jsonl").read_text())
    with pytest.raises(TraceStaleError, match=what):
        _replay(tmp_path, pack, **change)


def test_a_trace_is_refused_when_the_context_changed(tmp_path: Path, pack: ContextPack) -> None:
    _record(tmp_path, pack)
    changed = pack.model_copy(update={"rules": pack.rules[:-1], "truncated": ("rule x",)})
    with pytest.raises(TraceStaleError, match="context"):
        _replay(tmp_path, changed)


def test_a_trace_of_an_unfinished_run_is_refused(tmp_path: Path, pack: ContextPack) -> None:
    path = tmp_path / f"{REQUEST.id}.jsonl"
    path.write_text(
        dump_trace([request_event(REQUEST, SYSTEM), context_event(pack)]), encoding="utf-8"
    )
    with pytest.raises(TraceStaleError, match="did not finish"):
        _replay(tmp_path, pack)


def test_recorded_steps_over_the_current_limit_abort_the_replay(
    tmp_path: Path, pack: ContextPack
) -> None:
    two = RESULT.model_copy(update={"steps": (*RESULT.steps, *RESULT.steps)})
    events = [request_event(REQUEST, SYSTEM), context_event(pack), *step_events(two.steps)]
    (tmp_path / f"{REQUEST.id}.jsonl").write_text(
        dump_trace([*events, output_event(two)]), encoding="utf-8"
    )
    with pytest.raises(AgentLimitError, match="2 recorded tool calls, limit 1"):
        _replay(tmp_path, pack, limits=Limits(max_steps=1))
