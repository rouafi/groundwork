"""Command line entrypoint."""

from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from groundwork.core.domain.pack import PackConfig

app = typer.Typer(no_args_is_help=True, help="groundwork: an FDE deployment kit")

PACKS_DIR = Path("client_packs")


@app.command("validate-packs")
def validate_packs(packs_dir: Path = PACKS_DIR) -> None:
    """Validate every client pack config against the schema."""
    configs = sorted(packs_dir.glob("*/config.yaml")) if packs_dir.exists() else []
    invalid = 0
    for cfg in configs:
        try:
            PackConfig.model_validate(yaml.safe_load(cfg.read_text()))
        except ValidationError as exc:
            invalid += 1
            typer.echo(f"{cfg}: {exc}", err=True)
    typer.echo(f"{len(configs)} pack(s) checked, {invalid} invalid")
    if invalid:
        raise typer.Exit(code=1)


@app.command("mcp-serve")
def mcp_serve() -> None:
    """Serve the MCP context server over streamable HTTP."""
    from groundwork.entrypoints.mcp_server import mcp

    # Binding all interfaces is intended: the server runs inside a container.
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)  # noqa: S104


@app.command("demo")
def demo() -> None:
    """Replay recorded runs. Implemented in the harness milestone."""
    typer.echo("No recorded runs yet: traces/ is empty.")


@app.command("evals")
def evals() -> None:
    """Run golden sets. Implemented in the evals milestone."""
    typer.echo("No golden sets yet.")
