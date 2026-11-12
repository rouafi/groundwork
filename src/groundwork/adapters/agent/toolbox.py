"""The tools an agent may call: a small interface, and the pack's MCP server behind it.

`McpToolBox` talks to an `MCPServer` in memory, so the agent sees exactly the tools the
server registers (ADR 0008) and nothing else. Each tool carries the server's own
`read_only` annotation, which the agent checks before it starts.
"""

from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol, Self

from mcp import Client
from mcp.server.mcpserver import MCPServer


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool


class ToolBox(Protocol):
    """An async context manager that lists tools and calls them."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def list_tools(self) -> list[ToolSpec]: ...

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Return the tool's text result and whether it is an error."""
        ...


class McpToolBox:
    """The tools of one MCP server, reached through an in-memory client."""

    def __init__(self, server: MCPServer) -> None:
        self._server = server
        self._connection = Client(server)
        self._client: Any = None

    async def __aenter__(self) -> Self:
        self._client = await self._connection.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._connection.__aexit__(exc_type, exc, tb)

    async def list_tools(self) -> list[ToolSpec]:
        listing = await self._client.list_tools()
        return [
            ToolSpec(
                name=t.name,
                description=t.description or "",
                input_schema=dict(t.input_schema),
                read_only=bool(t.annotations and t.annotations.read_only_hint),
            )
            for t in listing.tools
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        result = await self._client.call_tool(name, arguments)
        text = "\n".join(block.text for block in result.content if hasattr(block, "text"))
        return text, bool(result.is_error)
