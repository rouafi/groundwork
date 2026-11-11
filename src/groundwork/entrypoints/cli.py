"""Command line entrypoint."""

from pathlib import Path

import typer

from groundwork.core.domain.errors import PackError
from groundwork.core.services.integrity import check_integrity
from groundwork.core.services.packs import load_domain_pack, load_pack_config
from groundwork.entrypoints.wiring import build_crm

app = typer.Typer(no_args_is_help=True, help="groundwork: an FDE deployment kit")

PACKS_DIR = Path("client_packs")
DOMAINS_DIR = Path("domains")


@app.command("validate-packs")
def validate_packs(packs_dir: Path = PACKS_DIR, domains_dir: Path = DOMAINS_DIR) -> None:
    """Validate every client pack: config, domain, CRM fixtures, references and vocabulary."""
    packs = _pack_dirs(packs_dir)
    invalid = 0
    for pack_dir in packs:
        problems = pack_problems(pack_dir, domains_dir)
        invalid += bool(problems)
        for problem in problems:
            typer.echo(problem, err=True)
    typer.echo(f"{len(packs)} pack(s) checked, {invalid} invalid")
    if invalid:
        raise typer.Exit(code=1)


def pack_problems(pack_dir: Path, domains_dir: Path) -> list[str]:
    """Every problem in one pack, each line starting with where it is."""
    try:
        config = load_pack_config(pack_dir)
        domain = load_domain_pack(domains_dir, config.domain)
        crm = build_crm(pack_dir, config)
    except PackError as exc:
        return [_located(pack_dir, exc.message)]
    return [_located(pack_dir, str(issue)) for issue in check_integrity(crm, domain)]


def _pack_dirs(packs_dir: Path) -> list[Path]:
    if not packs_dir.is_dir():
        return []
    return sorted(p for p in packs_dir.iterdir() if p.is_dir() and not p.name.startswith("."))


def _located(pack_dir: Path, message: str) -> str:
    return message if message.startswith(str(pack_dir)) else f"{pack_dir}: {message}"


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
