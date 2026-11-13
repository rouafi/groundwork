"""`groundwork evals` end to end, replaying runs recorded from scripted fakes."""

import dataclasses
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from groundwork.adapters.agent.passthrough import PassthroughAgent
from groundwork.adapters.model.recording import DEFAULT_SPECS, Recordings
from groundwork.adapters.model.replay import RecordingModel
from groundwork.core.services.evals.runner import run_pack
from groundwork.entrypoints.cli import app
from groundwork.entrypoints.evals_cli import build_eval_deps
from tests.evals_support import CaseAgent, EvalModel, email

REPO = Path(__file__).resolve().parents[2]
DOMAINS = REPO / "domains"
runner = CliRunner()

CASES = [
    {"id": "cli-1", "contact_id": "acme-c-1", "channel": "external", "draft": "Pro is 1490 EUR?",
     "must_contain": ["1490"], "expected_route": "approval", "tags": ["realistic"]},
    {"id": "cli-2", "contact_id": "acme-c-1", "channel": "internal", "draft": "Pro costs 1490 EUR.",
     "must_contain": ["1490"], "expected_route": "auto_send", "tags": ["realistic"]},
    {"id": "cli-3", "contact_id": "acme-c-4", "channel": "external", "draft": "Hello Malo.",
     "forbidden": [r"(?i)\d+\s?%\s?off"], "expected_route": "approval", "tags": ["injection"]},
]  # fmt: skip
CALIBRATION = [
    {"id": f"cal-{i}", "subject": "s", "body": f"body {i}", "human_tone": 4} for i in range(5)
]


@pytest.fixture(autouse=True)
def _replay_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GROUNDWORK_MODEL", "GROUNDWORK_EMBEDDING", "GROUNDWORK_RECORD"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Path]:
    """A copy of acme with a golden set, and the runs recorded from scripted fakes."""
    packs, traces, evals = tmp_path / "client_packs", tmp_path / "traces", tmp_path / "evals"
    shutil.copytree(REPO / "client_packs" / "acme", packs / "acme")
    shutil.copytree(REPO / "traces" / "acme" / "embeddings", traces / "acme" / "embeddings")
    pack = packs / "acme"
    (pack / "golden.jsonl").write_text("\n".join(json.dumps(c) for c in CASES) + "\n")
    (pack / "judge_calibration.jsonl").write_text(
        "\n".join(json.dumps(c) for c in CALIBRATION) + "\n"
    )
    (pack / "rubric.md").write_text("5 means warm, short and exact.\n")
    (pack / "thresholds.yaml").write_text("tone_mean_min: 4.0\n")

    deps = build_eval_deps(pack, DOMAINS, traces)
    model = RecordingModel(EvalModel(tone=4), Recordings(traces / "acme" / "model"), DEFAULT_SPECS)
    agent = CaseAgent({}, email("Insight Pro costs 1490.00 EUR."))
    flow = dataclasses.replace(deps.flow, agent=agent, model=model, write_traces=True)
    raw = dataclasses.replace(flow, agent=PassthroughAgent(), search=None, write_traces=False)
    run_pack(dataclasses.replace(deps, flow=flow, raw_flow=raw, judge_model=model))
    return {"packs": packs, "traces": traces, "evals": evals, "pack": pack}


def _evals(world: dict[str, Path], *extra: str) -> Result:
    args = ["evals", "--packs-dir", str(world["packs"]), "--domains-dir", str(DOMAINS),
            "--traces-dir", str(world["traces"]), "--evals-dir", str(world["evals"])]  # fmt: skip
    return runner.invoke(app, [*args, *extra])


def test_the_evals_replay_with_no_environment_and_pass(world: dict[str, Path]) -> None:
    result = _evals(world)
    assert result.exit_code == 0, result.output
    assert "acme: PASS, 3 case(s), tone 4.00" in result.output


def test_the_report_is_written_then_matches_a_regeneration(world: dict[str, Path]) -> None:
    written = _evals(world, "--write-report")
    assert written.exit_code == 0 and (world["evals"] / "report.md").is_file()
    assert (world["evals"] / "results" / "acme.json").is_file()
    assert _evals(world, "--check-report").exit_code == 0


def test_editing_the_report_by_hand_makes_the_check_fail(world: dict[str, Path]) -> None:
    _evals(world, "--write-report")
    report = world["evals"] / "report.md"
    report.write_text(report.read_text().replace("PASS", "PASS (really)", 1))
    result = _evals(world, "--check-report")
    assert result.exit_code == 1
    assert "report.md differs from a replay regeneration" in result.output
    assert "never edit by hand" in result.output


def test_a_missing_report_fails_the_check(world: dict[str, Path]) -> None:
    result = _evals(world, "--check-report")
    assert result.exit_code == 1 and "report.md is missing" in result.output


def test_raising_a_threshold_above_the_score_fails_naming_the_scorer_and_lowering_passes(
    world: dict[str, Path],
) -> None:
    thresholds = world["pack"] / "thresholds.yaml"
    thresholds.write_text("tone_mean_min: 4.5\n")
    failed = _evals(world)
    assert failed.exit_code == 1
    assert "FAIL tone_mean 4.00 is below tone_mean_min 4.50" in failed.output
    assert "thresholds not met: acme" in failed.output

    thresholds.write_text("tone_mean_min: 3.0\n")
    assert _evals(world).exit_code == 0


def test_a_judge_that_disagrees_with_the_human_labels_fails_the_run_explicitly(
    world: dict[str, Path],
) -> None:
    labels = [{**c, "human_tone": 1} for c in CALIBRATION]
    (world["pack"] / "judge_calibration.jsonl").write_text("\n".join(json.dumps(c) for c in labels))
    result = _evals(world)
    assert result.exit_code == 1
    assert "uncalibrated judge" in result.output and "never the labels" in result.output


def test_the_report_flags_need_every_pack(world: dict[str, Path]) -> None:
    result = _evals(world, "--pack", "acme", "--write-report")
    assert result.exit_code == 1 and "drop --pack" in result.output


def test_a_case_with_no_recorded_trace_names_how_to_record_it(world: dict[str, Path]) -> None:
    with (world["pack"] / "golden.jsonl").open("a") as golden:
        golden.write(json.dumps({**CASES[0], "id": "cli-unrecorded"}) + "\n")
    result = _evals(world)
    assert result.exit_code == 1 and "no recorded trace for case cli-unrecorded" in result.output


def test_a_pack_with_no_golden_set_is_reported(tmp_path: Path) -> None:
    (tmp_path / "client_packs").mkdir()
    result = runner.invoke(app, ["evals", "--packs-dir", str(tmp_path / "client_packs")])
    assert result.exit_code == 1 and "no pack with a golden set" in result.output


def test_unmet_thresholds_fail_unless_allowed_but_drift_always_fails(
    world: dict[str, Path],
) -> None:
    (world["pack"] / "thresholds.yaml").write_text("tone_mean_min: 5.0\n")
    assert _evals(world, "--write-report").exit_code == 1
    assert (world["evals"] / "report.md").is_file()

    strict = _evals(world, "--check-report")
    allowed = _evals(world, "--check-report", "--allow-unmet-thresholds")
    assert strict.exit_code == 1 and "thresholds not met: acme" in strict.output
    assert allowed.exit_code == 0 and "allowed by --allow-unmet-thresholds" in allowed.output

    (world["evals"] / "report.md").write_text("edited by hand\n")
    assert _evals(world, "--check-report", "--allow-unmet-thresholds").exit_code == 1
