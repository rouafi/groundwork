"""Command line entrypoint."""

import os
from pathlib import Path
from typing import Annotated

import typer

from groundwork.core.domain.errors import PackError
from groundwork.core.services.extraction import (
    PROMPT_NAMES,
    ExtractionPrompts,
    Workflow,
    extract_rules,
)
from groundwork.core.services.golden_checks import check_against_golden, golden_problems
from groundwork.core.services.integrity import check_integrity
from groundwork.core.services.packs import (
    load_domain_pack,
    load_extraction_golden,
    load_interviews,
    load_pack_config,
    load_prompt,
    load_rules,
)
from groundwork.core.services.rules_check import rule_problems
from groundwork.entrypoints.reports import summary, write_run
from groundwork.entrypoints.wiring import build_crm, build_model

app = typer.Typer(no_args_is_help=True, help="groundwork: an FDE deployment kit")

PACKS_DIR = Path("client_packs")
DOMAINS_DIR = Path("domains")
TRACES_DIR = Path("traces")
CONCURRENCY_ENV = "GROUNDWORK_MAX_CONCURRENCY"


@app.command("validate-packs")
def validate_packs(packs_dir: Path = PACKS_DIR, domains_dir: Path = DOMAINS_DIR) -> None:
    """Validate every client pack: config, domain, CRM facts, interviews, rules and claims."""
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
        interviews = {i.id: i for i in load_interviews(pack_dir)}
        rules = load_rules(pack_dir)
        golden = load_extraction_golden(pack_dir)
    except PackError as exc:
        return [_located(pack_dir, exc.message)]
    problems = [str(issue) for issue in check_integrity(crm, domain)]
    problems += rule_problems(rules, interviews, domain, crm)
    problems += golden_problems(golden, interviews) if golden else []
    return [_located(pack_dir, p) for p in problems]


@app.command("extract-rules")
def extract_rules_command(
    pack: Annotated[str, typer.Option(help="Client pack name under the packs directory.")],
    packs_dir: Path = PACKS_DIR,
    domains_dir: Path = DOMAINS_DIR,
    traces_dir: Path = TRACES_DIR,
    out_dir: Annotated[Path | None, typer.Option(help="Where to write; default: the pack.")] = None,
) -> None:
    """Propose rules from a pack's interviews. Writes proposals only, never rules.yaml."""
    pack_dir = packs_dir / pack
    try:
        config = load_pack_config(pack_dir)
        domain = load_domain_pack(domains_dir, config.domain)
        prompts = ExtractionPrompts(
            **{k: load_prompt(domains_dir, config.domain, n) for k, n in PROMPT_NAMES.items()}
        )
        workflow = Workflow(
            pack=pack,
            domain=domain,
            crm=build_crm(pack_dir, config),
            model=build_model(pack_dir, config, traces_dir),
            prompts=prompts,
        )
        interviews = load_interviews(pack_dir)
        golden = load_extraction_golden(pack_dir)
    except PackError as exc:
        typer.echo(_located(pack_dir, exc.message), err=True)
        raise typer.Exit(code=1) from exc
    concurrency = int(os.environ.get(CONCURRENCY_ENV, "4"))
    report = extract_rules(workflow, interviews, max_concurrency=concurrency)
    by_id = {i.id: i for i in interviews}
    checks = check_against_golden(report, golden, by_id) if golden else ()
    for path in write_run(report, out_dir or pack_dir):
        typer.echo(f"wrote {path}")
    for line in summary(report, checks):
        typer.echo(line)
    if report.failures:
        raise typer.Exit(code=1)


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
