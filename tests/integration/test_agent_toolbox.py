"""The agent's tools are the pack's MCP server, read-only, and nothing else."""

from pathlib import Path

import anyio

from groundwork.adapters.agent.toolbox import McpToolBox, ToolSpec
from groundwork.entrypoints.mcp_server import ALLOWED_TOOLS, create_server
from groundwork.entrypoints.wiring import build_server_context

ROOT = Path(__file__).resolve().parents[2]


def _toolbox() -> McpToolBox:
    context = build_server_context(
        ROOT / "client_packs" / "acme", ROOT / "domains", ROOT / "traces", {}
    )
    return McpToolBox(create_server(context))


def _run[T](use: object) -> T:
    async def main() -> T:
        async with _toolbox() as tools:
            return await use(tools)  # type: ignore[operator, no-any-return]

    return anyio.run(main)


def test_the_agent_sees_exactly_the_allowed_tools_and_all_are_read_only() -> None:
    async def listing(tools: McpToolBox) -> list[ToolSpec]:
        return await tools.list_tools()

    specs = _run(listing)
    assert {s.name for s in specs} == ALLOWED_TOOLS
    assert all(s.read_only for s in specs)
    assert all(s.input_schema.get("type") == "object" and s.description for s in specs)


def test_a_tool_call_returns_the_servers_text_and_not_an_error() -> None:
    async def call(tools: McpToolBox) -> tuple[str, bool]:
        return await tools.call("get_product_facts", {"product_ids": ["acme-p-2"]})

    text, is_error = _run(call)
    assert not is_error
    assert "Insight Pro" in text and "1490.00" in text


def test_a_failing_tool_call_is_reported_as_an_error_with_its_message() -> None:
    async def call(tools: McpToolBox) -> tuple[str, bool]:
        return await tools.call("get_product_facts", {"product_ids": ["acme-p-404"]})

    text, is_error = _run(call)
    assert is_error and "acme-p-404" in text
