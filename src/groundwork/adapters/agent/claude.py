"""ClaudeAgent: AgentPort as a small tool-use loop on the Messages API (ADR 0005).

The model gets the context and the pack's read-only tools. Each turn it either calls
tools, which the loop runs and answers, or gives its final answer: a JSON object that
the API constrains to the `HarmonizedEmail` schema. The loop owns the hard limits:
- steps: the number of tool calls; the call that would exceed it is not run;
- tokens: input plus output, over the whole run;
- time: a wall-clock timeout around everything.
Exceeding one raises `AgentLimitError`; an invalid or refused answer raises `AgentError`.
Nothing is sent or queued from here: the agent has no such tool.
"""

from collections.abc import Callable, Mapping
from typing import Any

import anthropic
import anyio
from pydantic import ValidationError

from groundwork.adapters.agent.toolbox import ToolBox, ToolSpec
from groundwork.adapters.model.recording import ModelSpec
from groundwork.core.domain.errors import AgentError, AgentLimitError
from groundwork.core.domain.harmonize import (
    AgentResult,
    AgentStep,
    ContextPack,
    HarmonizedEmail,
    HarmonizeRequest,
)
from groundwork.core.domain.harmonize_prompt import render_user_message
from groundwork.core.domain.knowhow import Usage
from groundwork.core.domain.policy import Limits

MAX_TOKENS = 4000
SUMMARY_CHARS = 200
TIER = "extraction"


class ClaudeAgent:
    """`client` is an `anthropic.AsyncAnthropic`; `toolbox` makes one tool box per run."""

    def __init__(
        self,
        client: Any,
        toolbox: Callable[[], ToolBox],
        specs: Mapping[str, ModelSpec],
        allowed_tools: frozenset[str],
    ) -> None:
        self._client = client
        self._toolbox = toolbox
        self._spec = specs[TIER]
        self._allowed = allowed_tools

    def run(
        self, *, system: str, context: ContextPack, request: HarmonizeRequest, limits: Limits
    ) -> AgentResult:
        return anyio.run(self._run, system, context, request, limits)

    async def _run(
        self, system: str, context: ContextPack, request: HarmonizeRequest, limits: Limits
    ) -> AgentResult:
        try:
            with anyio.fail_after(limits.timeout_s):
                async with self._toolbox() as tools:
                    specs = self._checked(await tools.list_tools())
                    return await self._loop(system, context, request, limits, tools, specs)
        except TimeoutError as exc:
            raise AgentLimitError("time", f"{limits.timeout_s:g} s") from exc

    def _checked(self, specs: list[ToolSpec]) -> list[ToolSpec]:
        """Fail closed: every tool must be allowed and read-only, or the run does not start."""
        for spec in specs:
            if spec.name not in self._allowed:
                raise AgentError(f"tool {spec.name!r} is not on the agent's allowlist")
            if not spec.read_only:
                raise AgentError(f"tool {spec.name!r} is not read-only: the agent may not use it")
        return specs

    async def _loop(
        self,
        system: str,
        context: ContextPack,
        request: HarmonizeRequest,
        limits: Limits,
        tools: ToolBox,
        specs: list[ToolSpec],
    ) -> AgentResult:
        schema = anthropic.transform_schema(HarmonizedEmail)
        params: dict[str, Any] = {
            "model": self._spec.model_id,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "tools": [_tool_param(s) for s in specs],
            "output_config": {"effort": self._spec.effort, "format": _format(schema)},
        }
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": render_user_message(context, request)}
        ]
        names = {s.name for s in specs}
        steps: list[AgentStep] = []
        usage = Usage()
        while True:
            response = await self._create(params, messages)
            usage = usage + _usage(response)
            total = usage.input_tokens + usage.output_tokens
            if total > limits.max_tokens:
                raise AgentLimitError("tokens", f"{total} tokens, limit {limits.max_tokens}")
            _check_stop(response)
            calls = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not calls:
                return AgentResult(email=_email(response), steps=tuple(steps), usage=usage)
            messages.append({"role": "assistant", "content": _assistant(response.content)})
            results = []
            for call in calls:
                if len(steps) + 1 > limits.max_steps:
                    raise AgentLimitError(
                        "steps", f"{len(steps) + 1} tool calls, limit {limits.max_steps}"
                    )
                arguments = dict(call.input)
                if call.name in names:
                    text, is_error = await tools.call(call.name, arguments)
                else:
                    text, is_error = f"tool {call.name!r} does not exist", True
                steps.append(
                    AgentStep(
                        tool=call.name, arguments=arguments, result_summary=_summary(text, is_error)
                    )
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": text,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": results})

    async def _create(self, params: dict[str, Any], messages: list[dict[str, Any]]) -> Any:
        try:
            return await self._client.beta.messages.create(**params, messages=messages)
        except anthropic.APIError as exc:
            raise AgentError(f"Claude API call failed: {exc}") from exc


def _format(schema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "json_schema", "schema": schema}


def _tool_param(spec: ToolSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "description": spec.description,
        "input_schema": spec.input_schema,
    }


def _assistant(content: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in content:
        if block.type == "text":
            blocks.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            blocks.append(
                {"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input)}
            )
    return blocks


def _check_stop(response: Any) -> None:
    if response.stop_reason == "refusal":
        raise AgentError("the model refused the request")
    if response.stop_reason == "max_tokens":
        raise AgentError(f"the model's answer was cut off at {MAX_TOKENS} tokens")


def _email(response: Any) -> HarmonizedEmail:
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    try:
        return HarmonizedEmail.model_validate_json(text)
    except ValidationError as exc:
        raise AgentError(f"the agent's answer is not a valid email: {exc}") from exc


def _usage(response: Any) -> Usage:
    usage = response.usage
    cached = (getattr(usage, "cache_creation_input_tokens", 0) or 0) + (
        getattr(usage, "cache_read_input_tokens", 0) or 0
    )
    return Usage(input_tokens=usage.input_tokens + cached, output_tokens=usage.output_tokens)


def _summary(text: str, is_error: bool) -> str:
    flat = " ".join(text.split())
    clipped = flat if len(flat) <= SUMMARY_CHARS else flat[: SUMMARY_CHARS - 1] + "…"
    return f"error: {clipped}" if is_error else clipped
