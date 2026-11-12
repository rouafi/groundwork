"""harmonize, approvals and demo end to end, replaying traces recorded from a scripted agent."""

import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from groundwork.adapters.agent.passthrough import PassthroughAgent
from groundwork.adapters.model.recording import DEFAULT_SPECS, Recordings
from groundwork.adapters.model.replay import RecordingModel
from groundwork.core.domain.harmonize import AgentResult, AgentStep, DemoCase, HarmonizedEmail
from groundwork.core.domain.knowhow import Usage
from groundwork.core.services.harmonize import harmonize
from groundwork.entrypoints.cli import app
from groundwork.entrypoints.wiring import build_flow
from tests.fakes import ScriptedAgent, StubModel

REPO = Path(__file__).resolve().parents[2]
DOMAINS = REPO / "domains"
runner = CliRunner()

CASES = [
    {"case_id": "internal-ok", "title": "A valid internal note", "contact_id": "acme-c-1",
     "channel": "internal", "draft": "Quick note: Pro is 1490 EUR."},
    {"case_id": "external-ok", "title": "A valid external email", "contact_id": "acme-c-1",
     "channel": "external", "draft": "Hi Ana, Pro is 1490 EUR."},
    {"case_id": "external-wrong", "title": "A wrong price", "contact_id": "acme-c-1",
     "channel": "external", "draft": "Hi Ana, Pro is 990 EUR."},
    {"case_id": "external-passthrough", "title": "A faulty agent", "contact_id": "acme-c-1",
     "channel": "external", "passthrough": True, "draft": "Hi Ana, Pro is 990 EUR, 50% off."},
]  # fmt: skip
BODIES = {
    "internal-ok": "Insight Pro costs 1490.00 EUR.",
    "external-ok": "Insight Pro costs 1490.00 EUR.",
    "external-wrong": "Insight Pro costs 990 EUR.",
    "external-passthrough": "unused: the passthrough agent writes the draft itself",
}


def _claims(**kwargs: Any) -> dict[str, Any]:
    wrong = "990" in (kwargs.get("document") or "")
    price = "990 EUR" if wrong else "1490 EUR"
    return {
        "claims": [
            {
                "text": f"Pro costs {price}.",
                "kind": "price",
                "product_id": "acme-p-2",
                "value": price,
            }
        ]
    }


@pytest.fixture(autouse=True)
def _replay_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GROUNDWORK_MODEL", "GROUNDWORK_EMBEDDING", "GROUNDWORK_RECORD"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Path]:
    """A copy of acme with demo cases, and traces recorded for them."""
    packs = tmp_path / "client_packs"
    shutil.copytree(REPO / "client_packs" / "acme", packs / "acme")
    (packs / "acme" / "demo_cases.json").write_text(json.dumps(CASES), encoding="utf-8")
    traces, var = tmp_path / "traces", tmp_path / "var"
    base = build_flow(packs / "acme", DOMAINS, traces, var, env={"GROUNDWORK_MODEL": "replay"})
    for item in CASES:
        step = AgentStep(
            tool="get_product_facts", arguments={"product_ids": ["acme-p-2"]}, result_summary="ok"
        )
        result = AgentResult(
            email=HarmonizedEmail(
                subject="Your quote", body=BODIES[item["case_id"]], rationale="Catalog."
            ),
            steps=(step,),
            usage=Usage(input_tokens=900, output_tokens=120),
        )
        recording = RecordingModel(
            StubModel(structured=_claims), Recordings(traces / "acme" / "model"), DEFAULT_SPECS
        )
        case = DemoCase.model_validate(item)
        agent: Any = PassthroughAgent() if case.passthrough else ScriptedAgent(result)
        flow = dataclasses.replace(base, agent=agent, model=recording)
        if case.passthrough:
            flow = dataclasses.replace(flow, search=None)
        harmonize(flow, case.request)
    shutil.rmtree(var, ignore_errors=True)
    return {"packs": packs, "traces": traces, "var": var}


def _base(world: dict[str, Path]) -> list[str]:
    return [
        "--packs-dir",
        str(world["packs"]),
        "--domains-dir",
        str(DOMAINS),
        "--traces-dir",
        str(world["traces"]),
    ]


def _demo(world: dict[str, Path]) -> Result:
    return runner.invoke(app, ["demo", "--pack", "acme", *_base(world)])


def test_the_demo_replays_the_traces_and_shows_the_three_routes(world: dict[str, Path]) -> None:
    result = _demo(world)
    assert result.exit_code == 0, result.output
    for decision in ("Decision: AUTO_SEND", "Decision: APPROVAL", "Decision: BLOCKED"):
        assert decision in result.output
    assert "acme: 4 case(s): 1 approval, 1 auto_send, 2 blocked" in result.output
    assert "Subject: (draft, unchanged)" in result.output
    assert "Draft:\n  Hi Ana, Pro is 990 EUR." in result.output
    assert "false claim" in result.output


def test_the_demo_leaves_no_queue_and_no_outbox_behind(world: dict[str, Path]) -> None:
    _demo(world)
    assert not world["var"].exists()


def test_the_demo_does_not_change_the_recorded_traces(world: dict[str, Path]) -> None:
    before = {p.name: p.read_bytes() for p in (world["traces"] / "acme").glob("*.jsonl")}
    _demo(world)
    assert {p.name: p.read_bytes() for p in (world["traces"] / "acme").glob("*.jsonl")} == before


def _harmonize(
    world: dict[str, Path], draft: str, case_id: str, tmp: Path, channel: str = "external"
) -> Result:
    file = tmp / "draft.txt"
    file.write_text(draft, encoding="utf-8")
    args = [
        "harmonize", "--pack", "acme", "--contact", "acme-c-1", "--channel", channel,
        "--draft", str(file), "--case-id", case_id, "--var-dir", str(world["var"]),
    ]  # fmt: skip
    return runner.invoke(app, [*args, *_base(world)])


def test_harmonize_queues_an_external_email_and_approving_sends_it_once(
    world: dict[str, Path], tmp_path: Path
) -> None:
    result = _harmonize(world, CASES[1]["draft"], "external-ok", tmp_path)
    assert result.exit_code == 0, result.output
    assert "Decision: APPROVAL" in result.output and "never sent automatically" in result.output
    var = ["--pack", "acme", "--var-dir", str(world["var"])]

    listing = runner.invoke(app, ["approvals", "list", *var])
    assert "external-ok" in listing.output and "1 pending" in listing.output
    assert not (world["var"] / "outbox").exists()

    sent = runner.invoke(
        app, ["approvals", "approve", "external-ok", *var, "--packs-dir", str(world["packs"])]
    )
    assert sent.exit_code == 0, sent.output
    outbox = (world["var"] / "outbox" / "acme.jsonl").read_text().splitlines()
    assert len(outbox) == 1 and json.loads(outbox[0])["subject"] == "Your quote"
    assert "0 pending" in runner.invoke(app, ["approvals", "list", *var]).output

    again = runner.invoke(
        app, ["approvals", "approve", "external-ok", *var, "--packs-dir", str(world["packs"])]
    )
    assert again.exit_code == 1 and "already approved" in again.output
    assert len((world["var"] / "outbox" / "acme.jsonl").read_text().splitlines()) == 1


def test_an_internal_email_is_sent_at_once(world: dict[str, Path], tmp_path: Path) -> None:
    result = _harmonize(world, CASES[0]["draft"], "internal-ok", tmp_path, "internal")
    assert result.exit_code == 0 and "Decision: AUTO_SEND" in result.output
    assert (world["var"] / "outbox" / "acme.jsonl").is_file()


def test_a_blocked_email_goes_nowhere(world: dict[str, Path], tmp_path: Path) -> None:
    result = _harmonize(world, CASES[2]["draft"], "external-wrong", tmp_path)
    assert result.exit_code == 0 and "Decision: BLOCKED" in result.output
    assert not world["var"].exists()


def test_rejecting_needs_a_reason_and_stores_it(world: dict[str, Path], tmp_path: Path) -> None:
    _harmonize(world, CASES[1]["draft"], "external-ok", tmp_path)
    var = ["--pack", "acme", "--var-dir", str(world["var"])]
    assert (
        runner.invoke(app, ["approvals", "reject", "external-ok", *var, "--reason", " "]).exit_code
        == 1
    )
    done = runner.invoke(app, ["approvals", "reject", "external-ok", *var, "--reason", "too pushy"])
    assert done.exit_code == 0 and "too pushy" in done.output
    assert not (world["var"] / "outbox").exists()


def test_a_draft_with_no_recorded_trace_says_how_to_record_it(
    world: dict[str, Path], tmp_path: Path
) -> None:
    result = _harmonize(world, "A brand new draft.", "never-recorded", tmp_path)
    assert result.exit_code == 1
    assert "no recorded trace for case never-recorded" in result.output
    assert "GROUNDWORK_MODEL=claude" in result.output


def test_a_changed_draft_is_refused_instead_of_replayed(
    world: dict[str, Path], tmp_path: Path
) -> None:
    result = _harmonize(world, "Not the recorded draft.", "external-ok", tmp_path)
    assert result.exit_code == 1 and "no longer matches the request" in result.output


def test_a_missing_draft_file_is_reported(world: dict[str, Path]) -> None:
    args = [
        "harmonize", "--pack", "acme", "--contact", "acme-c-1", "--channel", "external",
        "--draft", "nope.txt",
    ]  # fmt: skip
    result = runner.invoke(app, [*args, *_base(world)])
    assert result.exit_code == 1 and "draft file not found" in result.output


def test_validate_packs_checks_demo_cases_and_policies(world: dict[str, Path]) -> None:
    validate = ["validate-packs", "--packs-dir", str(world["packs"]), "--domains-dir", str(DOMAINS)]
    assert runner.invoke(app, validate).exit_code == 0

    cases = world["packs"] / "acme" / "demo_cases.json"
    cases.write_text(json.dumps([{**CASES[0], "contact_id": "acme-c-404"}]), encoding="utf-8")
    bad_contact = runner.invoke(app, validate)
    assert bad_contact.exit_code == 1
    assert "demo case internal-ok: unknown contact 'acme-c-404'" in bad_contact.output

    cases.write_text(json.dumps(CASES), encoding="utf-8")
    (world["packs"] / "acme" / "policies.yaml").write_text(
        "auto_send_external: true\n", encoding="utf-8"
    )
    bad_policy = runner.invoke(app, validate)
    assert bad_policy.exit_code == 1
    assert "policies.yaml" in bad_policy.output and "auto_send_external" in bad_policy.output
