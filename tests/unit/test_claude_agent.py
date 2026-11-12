import copy
import json
from types import SimpleNamespace
from typing import Any

import anthropic
import anyio
import httpx
import pytest

from groundwork.adapters.agent.claude import MAX_TOKENS, ClaudeAgent
from groundwork.adapters.agent.toolbox import ToolSpec
from groundwork.adapters.model.recording import DEFAULT_SPECS
from groundwork.core.domain.errors import AgentError, AgentLimitError
from groundwork.core.domain.harmonize import AgentResult, ContextPack, HarmonizeRequest
from groundwork.core.domain.policy import Limits
from tests.fakes import FakeToolBox

ALLOWED = frozenset({"get_rules", "get_product_facts"})
EMAIL = {"subject": "Your quote", "body": "Pro costs 1490.00 EUR.", "rationale": "Catalog price."}
REQUEST = HarmonizeRequest(contact_id="acme-c-1", channel="external", draft="Pro is 990 EUR.")


def _spec(name: str, read_only: bool = True) -> ToolSpec:
    return ToolSpec(
        name=name, description=f"{name} tool", input_schema={"type": "object"}, read_only=read_only
    )


def _text(text: str) -> Any:
    return SimpleNamespace(type="text", text=text)


def _use(id: str, name: str, **arguments: Any) -> Any:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=arguments)


def _reply(*blocks: Any, stop: str = "end_turn", inp: int = 100, out: int = 20) -> Any:
    usage = SimpleNamespace(
        input_tokens=inp,
        output_tokens=out,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    return SimpleNamespace(stop_reason=stop, content=list(blocks), usage=usage, model="m")


def _answer(**fields: Any) -> Any:
    return _reply(_text(json.dumps({**EMAIL, **fields})))


class FakeMessages:
    def __init__(self, script: list[Any], delay: float = 0.0) -> None:
        self._script = list(script)
        self._delay = delay
        self.calls: list[dict[str, Any]] = []

    async def create(self, **params: Any) -> Any:
        self.calls.append(copy.deepcopy(params))
        if self._delay:
            await anyio.sleep(self._delay)
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def _agent(
    script: list[Any],
    tools: FakeToolBox | None = None,
    delay: float = 0.0,
    allowed: frozenset[str] = ALLOWED,
) -> tuple[ClaudeAgent, FakeMessages, FakeToolBox]:
    messages = FakeMessages(script, delay)
    box = tools or FakeToolBox([_spec("get_rules"), _spec("get_product_facts")])
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return ClaudeAgent(client, lambda: box, DEFAULT_SPECS, allowed), messages, box


def _run(agent: ClaudeAgent, pack: ContextPack, limits: Limits | None = None) -> AgentResult:
    return agent.run(
        system="system prompt", context=pack, request=REQUEST, limits=limits or Limits()
    )


def test_a_direct_answer_has_no_steps(pack: ContextPack) -> None:
    agent, messages, box = _agent([_answer()])
    result = _run(agent, pack)
    assert result.email.subject == "Your quote"
    assert result.steps == () and box.calls == []
    assert (result.usage.input_tokens, result.usage.output_tokens) == (100, 20)
    assert len(messages.calls) == 1


def test_tool_calls_are_run_traced_and_answered(pack: ContextPack) -> None:
    script = [
        _reply(
            _text("Let me check."),
            _use("t1", "get_product_facts", product_ids=["acme-p-2"]),
            stop="tool_use",
        ),
        _answer(cited_nodes=["acme-p-2"]),
    ]
    box = FakeToolBox(
        [_spec("get_rules"), _spec("get_product_facts")],
        {"get_product_facts": ('[{"id": "acme-p-2", "price": "1490.00"}]', False)},
    )
    agent, messages, _ = _agent(script, box)
    result = _run(agent, pack)
    assert box.calls == [("get_product_facts", {"product_ids": ["acme-p-2"]})]
    (step,) = result.steps
    assert step.tool == "get_product_facts" and "1490.00" in step.result_summary
    assert result.email.cited_nodes == ("acme-p-2",)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (200, 40)
    second = messages.calls[1]["messages"]
    assert second[1]["role"] == "assistant"
    assert second[1]["content"][1] == {
        "type": "tool_use",
        "id": "t1",
        "name": "get_product_facts",
        "input": {"product_ids": ["acme-p-2"]},
    }
    assert second[2]["content"][0]["tool_use_id"] == "t1"
    assert second[2]["content"][0]["is_error"] is False


def test_the_request_carries_the_model_tools_system_prompt_and_schema(pack: ContextPack) -> None:
    agent, messages, _ = _agent([_answer()])
    _run(agent, pack)
    params = messages.calls[0]
    assert params["model"] == DEFAULT_SPECS["extraction"].model_id
    assert params["system"] == "system prompt"
    assert params["max_tokens"] == MAX_TOKENS
    assert [t["name"] for t in params["tools"]] == ["get_rules", "get_product_facts"]
    assert params["output_config"]["effort"] == DEFAULT_SPECS["extraction"].effort
    schema = params["output_config"]["format"]["schema"]
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert set(schema["required"]) == {"subject", "body", "rationale"}
    first = params["messages"][0]["content"]
    assert "<crm_data>" in first and "<rules>" in first and "Pro is 990 EUR." in first


def test_the_step_limit_stops_the_run_before_the_extra_tool_runs(pack: ContextPack) -> None:
    looping = [
        _reply(_use(f"t{i}", "get_rules", channel="external"), stop="tool_use") for i in range(5)
    ]
    agent, _, box = _agent(looping)
    with pytest.raises(AgentLimitError) as error:
        _run(agent, pack, Limits(max_steps=2))
    assert error.value.limit == "steps"
    assert "3 tool calls, limit 2" in str(error.value)
    assert len(box.calls) == 2


def test_several_tool_calls_in_one_turn_each_count_as_a_step(pack: ContextPack) -> None:
    turn = _reply(
        _use("a", "get_rules", channel="external"),
        _use("b", "get_rules", channel="internal"),
        stop="tool_use",
    )
    agent, _, box = _agent([turn])
    with pytest.raises(AgentLimitError, match="steps"):
        _run(agent, pack, Limits(max_steps=1))
    assert len(box.calls) == 1


def test_the_token_limit_counts_input_and_output_over_the_whole_run(pack: ContextPack) -> None:
    script = [
        _reply(_use("t1", "get_rules", channel="external"), stop="tool_use", inp=500, out=100),
        _reply(_use("t2", "get_rules", channel="external"), stop="tool_use", inp=600, out=100),
    ]
    agent, _, _ = _agent(script)
    with pytest.raises(AgentLimitError) as error:
        _run(agent, pack, Limits(max_tokens=1000))
    assert error.value.limit == "tokens"
    assert "1300 tokens, limit 1000" in str(error.value)


def test_the_timeout_aborts_the_run_with_an_explicit_error(pack: ContextPack) -> None:
    agent, _, _ = _agent([_answer()], delay=1.0)
    with pytest.raises(AgentLimitError) as error:
        _run(agent, pack, Limits(timeout_s=0.05))
    assert error.value.limit == "time"
    assert "0.05 s" in str(error.value)


def test_a_model_that_asks_for_a_missing_tool_gets_an_error_result_and_goes_on(
    pack: ContextPack,
) -> None:
    script = [_reply(_use("t1", "send_email", to="x"), stop="tool_use"), _answer()]
    agent, messages, box = _agent(script)
    result = _run(agent, pack)
    assert box.calls == []
    assert result.steps[0].result_summary.startswith("error: tool 'send_email' does not exist")
    assert messages.calls[1]["messages"][2]["content"][0]["is_error"] is True


def test_a_tool_error_is_passed_back_and_traced_as_an_error(pack: ContextPack) -> None:
    box = FakeToolBox([_spec("get_rules")], {"get_rules": ("unknown segment 'x'", True)})
    agent, messages, _ = _agent(
        [_reply(_use("t1", "get_rules", channel="external"), stop="tool_use"), _answer()], box
    )
    result = _run(agent, pack)
    assert result.steps[0].result_summary == "error: unknown segment 'x'"
    assert messages.calls[1]["messages"][2]["content"][0]["is_error"] is True


def test_a_long_tool_result_is_summarized(pack: ContextPack) -> None:
    box = FakeToolBox([_spec("get_rules")], {"get_rules": ("word " * 200, False)})
    agent, _, _ = _agent(
        [_reply(_use("t1", "get_rules", channel="external"), stop="tool_use"), _answer()], box
    )
    (step,) = _run(agent, pack).steps
    assert len(step.result_summary) <= 200 and step.result_summary.endswith("…")


@pytest.mark.parametrize(
    ("script", "needle"),
    [
        ([_reply(_text("not json"))], "not a valid email"),
        ([_reply(_text('{"subject": "s"}'))], "not a valid email"),
        ([_reply(stop="refusal")], "refused"),
        ([_reply(_text("{"), stop="max_tokens")], "cut off"),
    ],
)
def test_an_unusable_answer_is_an_agent_error(
    pack: ContextPack, script: list[Any], needle: str
) -> None:
    agent, _, _ = _agent(script)
    with pytest.raises(AgentError, match=needle):
        _run(agent, pack)


def test_an_api_failure_is_an_agent_error_naming_the_cause(pack: ContextPack) -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.AuthenticationError(
        "invalid x-api-key", response=httpx.Response(401, request=request), body=None
    )
    agent, _, _ = _agent([error])
    with pytest.raises(AgentError, match="Claude API call failed: invalid x-api-key"):
        _run(agent, pack)


def test_a_tool_that_writes_keeps_the_run_from_starting(pack: ContextPack) -> None:
    box = FakeToolBox([_spec("get_rules"), _spec("get_product_facts", read_only=False)])
    agent, messages, _ = _agent([_answer()], box)
    with pytest.raises(AgentError, match="not read-only"):
        _run(agent, pack)
    assert messages.calls == []


def test_a_tool_off_the_allowlist_keeps_the_run_from_starting(pack: ContextPack) -> None:
    box = FakeToolBox([_spec("get_rules"), _spec("send_email")])
    agent, messages, _ = _agent([_answer()], box)
    with pytest.raises(AgentError, match="'send_email' is not on the agent's allowlist"):
        _run(agent, pack)
    assert messages.calls == []
