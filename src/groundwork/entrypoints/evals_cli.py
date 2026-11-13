"""The `groundwork evals` command: run the golden sets, check the thresholds, write the report."""

import dataclasses
import os
from pathlib import Path
from typing import Annotated

import typer

from groundwork.adapters.agent.passthrough import PassthroughAgent
from groundwork.adapters.approval.memory import MemoryApproval
from groundwork.adapters.messaging.memory import MemoryMessaging
from groundwork.core.domain.errors import GroundworkError, PackError
from groundwork.core.domain.evals import PackResult
from groundwork.core.services.evals.judge import judge_system
from groundwork.core.services.evals.report import report_drift, write_outputs
from groundwork.core.services.evals.runner import EvalDeps, run_pack
from groundwork.core.services.packs import (
    GOLDEN_FILE,
    load_calibration,
    load_chunks,
    load_golden,
    load_pack_config,
    load_prompt,
    load_retrieval_questions,
    load_rubric,
    load_thresholds,
)
from groundwork.core.services.retrieval import search_knowhow
from groundwork.entrypoints.wiring import (
    EMBEDDING_ENV,
    MODEL_ENV,
    PASSAGES,
    RECORD_ENV,
    RECORD_ON,
    RECORD_RESUME,
    build_flow,
    build_server_context,
)

PACKS_DIR = Path("client_packs")
DOMAINS_DIR = Path("domains")
TRACES_DIR = Path("traces")
EVALS_DIR = Path("evals")
JUDGE_PROMPT = "judge_email"


def build_eval_deps(pack_dir: Path, domains_dir: Path, traces_dir: Path) -> EvalDeps:
    """Everything the evals of one pack need. Raises `GroundworkError` on a bad pack.

    Both flows send and queue into memory, so an eval never touches `var/`.
    """
    config = load_pack_config(pack_dir)
    cases = load_golden(pack_dir)
    thresholds, rubric = load_thresholds(pack_dir), load_rubric(pack_dir)
    if not cases or thresholds is None or rubric is None:
        raise PackError(f"{pack_dir}: needs golden.jsonl, thresholds.yaml and rubric.md")
    server = build_server_context(pack_dir, domains_dir, traces_dir)
    flow = dataclasses.replace(
        build_flow(pack_dir, domains_dir, traces_dir, Path("var")),
        messaging=MemoryMessaging(),
        approval=MemoryApproval(),
    )
    raw_flow = dataclasses.replace(flow, agent=PassthroughAgent(), search=None, write_traces=False)
    questions = load_retrieval_questions(pack_dir)
    search = None
    if server.indexed_chunks and questions:

        def search(query: str):  # type: ignore[no-untyped-def]
            return search_knowhow(query, server.store, server.embedding(), PASSAGES)

    approved = tuple(r for r in server.rules if r.status == "approved")
    known = {r.id for r in approved} | set(server.crm.list_product_ids())
    known |= {c.id for c in load_chunks(pack_dir)}
    return EvalDeps(
        pack=pack_dir.name,
        cases=cases,
        thresholds=thresholds,
        calibration=load_calibration(pack_dir),
        flow=flow,
        raw_flow=raw_flow,
        judge_model=flow.model,
        judge_system=judge_system(load_prompt(domains_dir, config.domain, JUDGE_PROMPT), rubric),
        rules=approved,
        known_nodes=frozenset(known),
        questions=questions,
        search=search,
    )


def evals_command(
    pack: Annotated[list[str] | None, typer.Option(help="Pack(s) to run; default: all.")] = None,
    write_report: Annotated[
        bool, typer.Option(help="Regenerate evals/report.md and results.")
    ] = False,
    check_report: Annotated[
        bool, typer.Option(help="Fail if the committed report differs.")
    ] = False,
    model: Annotated[str | None, typer.Option(help="claude runs live; default: replay.")] = None,
    record: Annotated[bool, typer.Option(help="Record model calls and embeddings.")] = False,
    allow_unmet_thresholds: Annotated[
        bool,
        typer.Option(help="Report unmet thresholds without failing (drift still fails)."),
    ] = False,
    resume: Annotated[
        bool,
        typer.Option(help="Like --record, but only for what has no valid recording yet."),
    ] = False,
    packs_dir: Path = PACKS_DIR,
    domains_dir: Path = DOMAINS_DIR,
    traces_dir: Path = TRACES_DIR,
    evals_dir: Path = EVALS_DIR,
) -> None:
    """Run each pack's golden set through the harness and check its thresholds.

    Replays the recorded runs by default (no key). Exit code 1 if a threshold fails, the
    judge is uncalibrated, or `--check-report` finds the committed report out of date.
    `--model claude` is live and costs money; with `--record` the runs are recorded afresh,
    with `--resume` only the cases and calls with no valid recording are run live.
    `--allow-unmet-thresholds` is for CI while a pack is below its thresholds: the report
    drift still fails, the thresholds are only printed.
    """
    if (write_report or check_report) and pack:
        raise _fail("--write-report and --check-report need every pack: drop --pack")
    if resume and model != "claude":
        raise _fail("--resume re-records live: add --model claude (it costs money)")
    if record and resume:
        raise _fail("--record and --resume are exclusive: --resume keeps valid recordings")
    if model:
        os.environ[MODEL_ENV] = model
        if model == "claude":
            os.environ.setdefault(EMBEDDING_ENV, "voyage")
        elif model == "replay":
            os.environ[EMBEDDING_ENV] = "replay"  # a replay never reaches a paid API
    if record or resume:
        os.environ[RECORD_ENV] = RECORD_RESUME if resume else RECORD_ON
    names = pack or sorted(p.name for p in packs_dir.iterdir() if (p / GOLDEN_FILE).is_file())
    if not names:
        raise _fail(f"no pack with a golden set under {packs_dir}")

    results: list[PackResult] = []
    for name in names:
        try:
            results.append(run_pack(build_eval_deps(packs_dir / name, domains_dir, traces_dir)))
        except GroundworkError as exc:
            raise _fail(f"{packs_dir / name}: {exc}") from exc
    for result in results:
        for line in _summary(result):
            typer.echo(line)

    failed = [r.pack for r in results if not r.passed]
    if write_report:
        for path in write_outputs(results, evals_dir):
            typer.echo(f"wrote {path}")
    if check_report:
        drift = report_drift(results, evals_dir)
        for problem in drift:
            typer.echo(problem, err=True)
        if drift:
            typer.echo(
                "regenerate with `groundwork evals --write-report`; never edit by hand", err=True
            )
            raise typer.Exit(code=1)
    if failed:
        typer.echo(f"thresholds not met: {', '.join(failed)}", err=True)
        if not allow_unmet_thresholds:
            raise typer.Exit(code=1)
        typer.echo("allowed by --allow-unmet-thresholds: see docs/evals.md", err=True)


def _summary(result: PackResult) -> list[str]:
    m = result.metrics
    lines = [
        f"{result.pack}: {'PASS' if result.passed else 'FAIL'}, {m.cases} case(s), "
        f"tone {m.tone_mean:.2f} (raw {m.raw_tone_mean:.2f}), "
        f"false claims {m.fact_false_claims} (raw {m.raw_false_claims}), "
        f"routing {m.routing_accuracy:.2f}, traceability {m.traceability:.2f}"
    ]
    lines += [f"  FAIL {t.message}" for t in result.thresholds if not t.passed]
    lines += [f"  note: {n}" for n in result.notes]
    return lines


def _fail(message: str) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=1)
