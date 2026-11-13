"""Commands of the client playbook (docs/playbook.md)."""

from pathlib import Path
from typing import Annotated

import typer

from groundwork.core.domain.errors import GroundworkError
from groundwork.core.services.scaffold import scaffold_pack

PACKS_DIR = Path("client_packs")
DOMAINS_DIR = Path("domains")
PLAYBOOK_DIR = Path("playbook")


def new_pack_command(
    client: Annotated[str, typer.Argument(help="Client name: lowercase letters, digits, dashes.")],
    domain: Annotated[str, typer.Option(help="Domain pack the client uses.")] = "comms",
    packs_dir: Path = PACKS_DIR,
    domains_dir: Path = DOMAINS_DIR,
    playbook_dir: Path = PLAYBOOK_DIR,
) -> None:
    """Create client_packs/<client>/ from the playbook templates. Data only, never overwrites."""
    try:
        created = scaffold_pack(client, domain, packs_dir, domains_dir, playbook_dir)
    except GroundworkError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    for path in created:
        typer.echo(f"created {path}")
    discovery = packs_dir / client / "discovery.yaml"
    typer.echo(f"\nNext: fill {discovery} with the sponsor, then check it with")
    typer.echo(f"  uv run groundwork validate-packs --pack {client} --stage day1")
    typer.echo("The sponsor's sign-off is recorded by a person, in that file.")
