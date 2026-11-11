"""MCP context server entrypoint. Tools are added as ports get adapters."""

from mcp.server.mcpserver import MCPServer

mcp: MCPServer = MCPServer("groundwork")


@mcp.tool()
def ping() -> str:
    """Health check tool."""
    return "pong"
