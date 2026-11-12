"""Commands of the harmonization harness: harmonize, approvals, demo."""

import dataclasses
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from groundwork.adapters.agent.passthrough import PassthroughAgent
from groundwork.adapters.approval.file import FileApproval
from groundwork.adapters.messaging.console import ConsoleMessaging
from groundwork.core.domain.errors import GroundworkError, PackError
from groundwork.core.domain.harmonize import HarmonizeRequest, MessageChannel
from groundwork.core.services.approvals import approve, reject
from groundwork.core.services.harmonize import harmonize
from groundwork.core.services.packs import load_demo_cases
from groundwork.entrypoints.reports import outcome_lines
from groundwork.entrypoints.wiring import (
    EMBEDDING_ENV,
    MODEL_ENV,
    RECORD_ENV,
    build_flow,
)

PACKS_DIR = Path("client_packs")
DOMAINS_DIR = Path("domains")
TRACES_DIR = Path("traces")
VAR_DIR = Path("var")

approvals_app = typer.Typer(no_args_is_help=True, help="Emails waiting for a human")


def _fail(message: str) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=1)


def harmonize_command(
    pack: Annotated[str, typer.Option(help="Client pack name under the packs directory.")],
    contact: Annotated[str, typer.Option(help="CRM id of the contact the email is for.")],
    channel: Annotated[MessageChannel, typer.Option(help="internal or external.")],
    draft: Annotated[Path, typer.Option(help="Text file holding the draft to rewrite.")],
    case_id: Annotated[str | None, typer.Option(help="Name of the trace; default: a hash.")] = None,
    packs_dir: Path = PACKS_DIR,
    domains_dir: Path = DOMAINS_DIR,
    traces_dir: Path = TRACES_DIR,
    var_dir: Path = VAR_DIR,
) -> None:
    """Rewrite a draft with the agent, check it, and route it: send, approval or blocked."""
    pack_dir = packs_dir / pack
    if not draft.is_file():
        raise _fail(f"{draft}: draft file not found")
    try:
        request = HarmonizeRequest(
            contact_id=contact, channel=channel, draft=draft.read_text(encoding="utf-8"),
            case_id=case_id,
        )  # fmt: skip
        flow = build_flow(pack_dir, domains_dir, traces_dir, var_dir)
        outcome = harmonize(flow, request)
    except GroundworkError as exc:
        raise _fail(f"{pack_dir}: {exc}") from exc
    for line in outcome_lines(request, outcome, flow.traces_dir / f"{request.id}.jsonl"):
        typer.echo(line)


@approvals_app.command("list")
def approvals_list(
    pack: Annotated[str, typer.Option(help="Client pack name.")], var_dir: Path = VAR_DIR
) -> None:
    """List the emails waiting for approval."""
    try:
        pending = FileApproval(pack, var_dir).list_pending()
    except GroundworkError as exc:
        raise _fail(str(exc)) from exc
    for item in pending:
        typer.echo(f'{item.id}  to {item.recipient}  "{item.email.subject}"')
        for reason in item.decision.reasons:
            typer.echo(f"    - {reason}")
    typer.echo(f"{len(pending)} pending")


@approvals_app.command("show")
def approvals_show(
    id: Annotated[str, typer.Argument(help="Approval id (the case id).")],
    pack: Annotated[str, typer.Option(help="Client pack name.")],
    var_dir: Path = VAR_DIR,
) -> None:
    """Show a pending email in full, with why it waits: read it before you decide."""
    try:
        item = next((i for i in FileApproval(pack, var_dir).list_pending() if i.id == id), None)
    except GroundworkError as exc:
        raise _fail(str(exc)) from exc
    if item is None:
        raise _fail(f"approval {id!r} is not pending (see: approvals list)")
    typer.echo(f"To: {item.recipient}\nSubject: {item.email.subject}\n\n{item.email.body}\n")
    typer.echo(f"Why it was written this way: {item.email.rationale}")
    typer.echo("Why it waits for you:")
    for reason in item.decision.reasons:
        typer.echo(f"  - {reason}")


@approvals_app.command("approve")
def approvals_approve(
    id: Annotated[str, typer.Argument(help="Approval id (the case id).")],
    pack: Annotated[str, typer.Option(help="Client pack name.")],
    var_dir: Path = VAR_DIR,
) -> None:
    """Approve an email and send it to the recipient fixed when it was queued. Once only."""
    try:
        item = approve(id, FileApproval(pack, var_dir), ConsoleMessaging(pack, var_dir))
    except GroundworkError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"approved and sent: {item.id}")


@approvals_app.command("reject")
def approvals_reject(
    id: Annotated[str, typer.Argument(help="Approval id (the case id).")],
    pack: Annotated[str, typer.Option(help="Client pack name.")],
    reason: Annotated[str, typer.Option(help="Why the email is rejected.")],
    var_dir: Path = VAR_DIR,
) -> None:
    """Reject an email, with a reason. Nothing is sent."""
    try:
        item = reject(id, reason, FileApproval(pack, var_dir))
    except GroundworkError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"rejected: {item.id} ({item.reason})")


def demo_command(
    pack: Annotated[list[str] | None, typer.Option(help="Pack(s) to run; default: all.")] = None,
    case: Annotated[list[str] | None, typer.Option(help="Case id(s) to run; default: all.")] = None,
    model: Annotated[str | None, typer.Option(help="claude runs live; default: replay.")] = None,
    record: Annotated[bool, typer.Option(help="Record model calls and embeddings.")] = False,
    packs_dir: Path = PACKS_DIR,
    domains_dir: Path = DOMAINS_DIR,
    traces_dir: Path = TRACES_DIR,
) -> None:
    """Run each pack's demo cases and show the draft, the email and the decision.

    Replays the recorded traces by default (no key). Emails go to a temporary folder,
    so a demo never leaves a queue behind. `--model claude` is live and costs money;
    with `--record` the traces and recordings are written for the next replay.
    """
    if model:
        os.environ[MODEL_ENV] = model
        if model == "claude":
            os.environ.setdefault(EMBEDDING_ENV, "voyage")
    if record:
        os.environ[RECORD_ENV] = "1"
    names = pack or sorted(p.name for p in packs_dir.iterdir() if (p / "demo_cases.json").is_file())
    if not names:
        raise _fail(f"no pack with demo cases under {packs_dir}")
    with tempfile.TemporaryDirectory(prefix="groundwork-demo-") as scratch:
        for name in names:
            _run_pack(packs_dir / name, domains_dir, traces_dir, Path(scratch), case)


def _run_pack(
    pack_dir: Path, domains_dir: Path, traces_dir: Path, var_dir: Path, only: list[str] | None
) -> None:
    try:
        cases = load_demo_cases(pack_dir)
        if not cases:
            raise PackError(f"{pack_dir}: no demo cases (demo_cases.json)")
        if only:
            cases = tuple(c for c in cases if c.case_id in only)
            if not cases:
                raise PackError(f"{pack_dir}: none of the cases {only} exists")
        flow = build_flow(pack_dir, domains_dir, traces_dir, var_dir)
        routes: Counter[str] = Counter()
        for case in cases:
            typer.echo(f"\n== {pack_dir.name} / {case.case_id}: {case.title} ({case.channel}) ==")
            typer.echo("Draft:")
            typer.echo(f"  {case.draft}")
            run = flow
            if case.passthrough:
                run = dataclasses.replace(flow, agent=PassthroughAgent(), search=None)
            outcome = harmonize(run, case.request)
            routes[outcome.decision.route] += 1
            path = flow.traces_dir / f"{case.case_id}.jsonl"
            for line in outcome_lines(case.request, outcome, path):
                typer.echo(line)
    except GroundworkError as exc:
        raise _fail(f"{pack_dir}: {exc}") from exc
    shown = ", ".join(f"{n} {route}" for route, n in sorted(routes.items()))
    typer.echo(f"\n{pack_dir.name}: {len(cases)} case(s): {shown}")
