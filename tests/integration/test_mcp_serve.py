"""`groundwork mcp-serve`: the real command, as Claude Desktop starts it, over stdio."""

import os
import sys
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters
from typer.testing import CliRunner

from groundwork.entrypoints.cli import app
from groundwork.entrypoints.mcp_server import ALLOWED_TOOLS

REPO = Path(__file__).resolve().parents[2]
GROUNDWORK = Path(sys.executable).parent / "groundwork"
runner = CliRunner()


def test_the_stdio_server_starts_and_answers_a_tool_call() -> None:
    params = StdioServerParameters(
        command=str(GROUNDWORK),
        args=["mcp-serve", "--pack", "acme", "--transport", "stdio"],
        cwd=REPO,
        env={"PATH": os.environ.get("PATH", ""), "GROUNDWORK_MODEL": "replay"},
    )

    async def main() -> tuple[set[str], str]:
        with anyio.fail_after(30):
            async with Client(params) as client:
                tools = await client.list_tools()
                result = await client.call_tool("get_contact_context", {"contact_id": "acme-c-1"})
                assert not result.is_error, result.content
                assert result.structured_content is not None
                return {t.name for t in tools.tools}, result.structured_content["contact"]["id"]

    names, contact_id = anyio.run(main)
    assert names == ALLOWED_TOOLS
    assert contact_id == "acme-c-1"


def test_an_unknown_pack_is_explained_before_serving(tmp_path: Path) -> None:
    result = runner.invoke(app, ["mcp-serve", "--pack", "nope", "--packs-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "nope" in result.output


def test_an_unknown_transport_is_rejected() -> None:
    result = runner.invoke(app, ["mcp-serve", "--pack", "acme", "--transport", "sse"])
    assert result.exit_code == 2
    assert "transport" in result.output.casefold()
