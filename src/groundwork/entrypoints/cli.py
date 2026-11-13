"""Command line entrypoint."""

import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from groundwork.core.domain.errors import GroundworkError, PackError
from groundwork.core.services.extraction import (
    PROMPT_NAMES,
    ExtractionPrompts,
    Workflow,
    extract_rules,
)
from groundwork.core.services.golden_checks import check_against_golden, golden_problems
from groundwork.core.services.indexing import (
    build_index,
    chunk_problems,
    dump_chunks,
    question_problems,
)
from groundwork.core.services.integrity import (
    check_integrity,
    demo_problems,
    golden_case_problems,
)
from groundwork.core.services.packs import (
    CHUNKS_FILE,
    load_calibration,
    load_chunks,
    load_demo_cases,
    load_domain_pack,
    load_extraction_golden,
    load_golden,
    load_interviews,
    load_pack_config,
    load_pack_policies,
    load_prompt,
    load_retrieval_questions,
    load_rubric,
    load_rules,
    load_thresholds,
)
from groundwork.core.services.rules_check import rule_problems
from groundwork.entrypoints.evals_cli import evals_command
from groundwork.entrypoints.harness_cli import approvals_app, demo_command, harmonize_command
from groundwork.entrypoints.mcp_server import create_server
from groundwork.entrypoints.playbook_cli import new_pack_command
from groundwork.entrypoints.reports import summary, write_run
from groundwork.entrypoints.stages import Stage, stage_problems
from groundwork.entrypoints.wiring import (
    CONTEXT_PROMPT,
    build_crm,
    build_embedding,
    build_messaging,
    build_model,
    build_server_context,
)

app = typer.Typer(no_args_is_help=True, help="groundwork: an FDE deployment kit")
app.command("harmonize")(harmonize_command)
app.command("new-pack")(new_pack_command)
app.command("demo")(demo_command)
app.command("evals")(evals_command)
app.add_typer(approvals_app, name="approvals")

PACKS_DIR = Path("client_packs")
DOMAINS_DIR = Path("domains")
TRACES_DIR = Path("traces")
CONCURRENCY_ENV = "GROUNDWORK_MAX_CONCURRENCY"


@app.command("validate-packs")
def validate_packs(
    packs_dir: Path = PACKS_DIR,
    domains_dir: Path = DOMAINS_DIR,
    traces_dir: Path = TRACES_DIR,
    pack: Annotated[str | None, typer.Option(help="Validate only this pack.")] = None,
    stage: Annotated[
        Stage | None,
        typer.Option(help="Check what days 1 to N of the playbook must have produced."),
    ] = None,
) -> None:
    """Validate client packs: everything, or with --stage what a playbook day must have produced."""
    packs = _pack_dirs(packs_dir)
    if pack is not None:
        packs = [p for p in packs if p.name == pack]
        if not packs:
            typer.echo(f"{packs_dir / pack}: no such pack", err=True)
            raise typer.Exit(code=1)
    invalid = 0
    for pack_dir in packs:
        problems = (
            [
                _located(pack_dir, p)
                for p in stage_problems(pack_dir, stage, domains_dir, traces_dir)
            ]
            if stage
            else pack_problems(pack_dir, domains_dir)
        )
        invalid += bool(problems)
        for problem in problems:
            typer.echo(problem, err=True)
    where = f" at {stage.value}" if stage else ""
    typer.echo(f"{len(packs)} pack(s) checked{where}, {invalid} invalid")
    if invalid:
        raise typer.Exit(code=1)


def pack_problems(pack_dir: Path, domains_dir: Path) -> list[str]:
    """Every problem in one pack, each line starting with where it is."""
    try:
        config = load_pack_config(pack_dir)
        domain = load_domain_pack(domains_dir, config.domain)
        crm = build_crm(pack_dir, config)
        build_messaging(pack_dir, config, Path("var"))
        interviews = {i.id: i for i in load_interviews(pack_dir)}
        rules = load_rules(pack_dir)
        golden = load_extraction_golden(pack_dir)
        chunks = load_chunks(pack_dir)
        questions = load_retrieval_questions(pack_dir)
        demo_cases = load_demo_cases(pack_dir)
        golden_cases = load_golden(pack_dir)
        thresholds = load_thresholds(pack_dir)
        rubric = load_rubric(pack_dir)
        calibration = load_calibration(pack_dir)
        load_pack_policies(pack_dir)
    except PackError as exc:
        return [_located(pack_dir, exc.message)]
    problems = [str(issue) for issue in check_integrity(crm, domain)]
    problems += rule_problems(rules, interviews, domain, crm)
    problems += golden_problems(golden, interviews) if golden else []
    problems += chunk_problems(chunks, interviews)
    problems += question_problems(questions, interviews)
    problems += demo_problems(demo_cases, crm)
    problems += golden_case_problems(
        golden_cases, crm, thresholds is not None, rubric is not None, bool(calibration)
    )
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
    except GroundworkError as exc:
        typer.echo(_located(pack_dir, str(exc)), err=True)
        raise typer.Exit(code=1) from exc
    concurrency = _concurrency()
    report = extract_rules(workflow, interviews, max_concurrency=concurrency)
    by_id = {i.id: i for i in interviews}
    checks = check_against_golden(report, golden, by_id) if golden else ()
    for path in write_run(report, out_dir or pack_dir):
        typer.echo(f"wrote {path}")
    for line in summary(report, checks):
        typer.echo(line)
    if report.failures:
        raise typer.Exit(code=1)


@app.command("index")
def index_command(
    pack: Annotated[str, typer.Option(help="Client pack name under the packs directory.")],
    packs_dir: Path = PACKS_DIR,
    domains_dir: Path = DOMAINS_DIR,
    traces_dir: Path = TRACES_DIR,
    out_dir: Annotated[Path | None, typer.Option(help="Where to write; default: the pack.")] = None,
) -> None:
    """Index a pack's interviews for search: chunk, contextualize, embed (never CRM facts)."""
    pack_dir = packs_dir / pack
    try:
        config = load_pack_config(pack_dir)
        system = load_prompt(domains_dir, config.domain, CONTEXT_PROMPT)
        interviews = load_interviews(pack_dir)
        if not interviews:
            raise PackError(f"{pack_dir}: no interviews to index")
        model = build_model(pack_dir, config, traces_dir)
        embedding = build_embedding(pack_dir, config, traces_dir)
        chunks, usage = build_index(interviews, model, embedding, system)
        # The pack's retrieval questions are embedded too: with GROUNDWORK_RECORD=1 that
        # records them, so replay can answer them; in replay it checks they are recorded.
        embedding.embed([q.question for q in load_retrieval_questions(pack_dir)], "query")
    except GroundworkError as exc:
        typer.echo(_located(pack_dir, str(exc)), err=True)
        raise typer.Exit(code=1) from exc
    path = (out_dir or pack_dir) / CHUNKS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_chunks(chunks), encoding="utf-8")
    typer.echo(f"wrote {path}")
    typer.echo(
        f"{pack}: {len(chunks)} chunk(s) from {len(interviews)} interview(s), "
        f"{usage.input_tokens} input / {usage.output_tokens} output tokens"
    )


def _concurrency() -> int:
    value = os.environ.get(CONCURRENCY_ENV, "4")
    if not value.isdigit() or int(value) < 1:
        typer.echo(f"{CONCURRENCY_ENV} must be a positive integer, got {value!r}", err=True)
        raise typer.Exit(code=1)
    return int(value)


def _pack_dirs(packs_dir: Path) -> list[Path]:
    if not packs_dir.is_dir():
        return []
    return sorted(p for p in packs_dir.iterdir() if p.is_dir() and not p.name.startswith("."))


def _located(pack_dir: Path, message: str) -> str:
    return message if message.startswith(str(pack_dir)) else f"{pack_dir}: {message}"


class Transport(StrEnum):
    """How an MCP client reaches the server."""

    stdio = "stdio"
    streamable_http = "streamable-http"


MCP_HTTP_PORT = 8001


@app.command("mcp-serve")
def mcp_serve(
    pack: Annotated[str, typer.Option(help="Client pack the server reads, fixed at start.")],
    transport: Annotated[
        Transport, typer.Option(help="stdio for Claude Desktop, streamable-http for a service.")
    ] = Transport.streamable_http,
    packs_dir: Path = PACKS_DIR,
    domains_dir: Path = DOMAINS_DIR,
    traces_dir: Path = TRACES_DIR,
) -> None:
    """Serve one pack's read-only context tools (MCP). Nothing is written to stdout on stdio."""
    pack_dir = packs_dir / pack
    try:
        context = build_server_context(pack_dir, domains_dir, traces_dir)
    except PackError as exc:
        typer.echo(_located(pack_dir, exc.message), err=True)
        raise typer.Exit(code=1) from exc
    server = create_server(context)
    if transport is Transport.stdio:
        server.run(transport="stdio")
        return
    # Binding all interfaces is intended: the server runs inside a container.
    server.run(transport="streamable-http", host="0.0.0.0", port=MCP_HTTP_PORT)  # noqa: S104
