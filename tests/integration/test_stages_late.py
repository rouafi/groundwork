"""validate-packs --stage day4 and day5.

Day 4 runs on a pack scaffolded by `new-pack` in a temporary folder. Day 5 runs the evals on
the recorded runs of the shipped acme pack, copied into a temporary folder; the thresholds
written there are test data that prove the check can pass and fail, and the thresholds of the
shipped packs are never touched.
"""

import json
import os
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner, Result

from groundwork.entrypoints.cli import app

REPO = Path(__file__).resolve().parents[2]
ACME = REPO / "client_packs" / "acme"
runner = CliRunner()

SIGNED = {
    "client": "acme",
    "sponsor": "Head of customer success",
    "use_case": "Harmonize customer emails.",
    "users": ["account managers"],
    "channels": ["internal", "external"],
    "systems": [{"name": "HubSpot", "role": "contacts and deals"}],
    "success_metric": {"name": "corrections", "baseline": "30%", "target": "10%"},
    "risks": ["a wrong price reaches a customer"],
    "status": "signed_off",
    "signed_off_by": "Ana Silva",
}
MET = {  # test data: thresholds any run meets, to prove day 5 can pass
    "fact_false_claims": 1000,
    "rule_violations": 1000,
    "tone_mean_min": 1.0,
    "routing_accuracy_min": 0.0,
    "traceability_min": 0.0,
    "retrieval_recall_at_5_min": 0.0,
    "judge_agreement_min": 0.0,
}
UNMET = {**MET, "tone_mean_min": 5.0, "fact_false_claims": 0}


def _validate(packs: Path, stage: str, pack: str) -> Result:
    args = ["validate-packs", "--packs-dir", str(packs), "--domains-dir", str(REPO / "domains"),
            "--traces-dir", str(REPO / "traces"), "--pack", pack, "--stage", stage]  # fmt: skip
    return runner.invoke(app, args)


def _plain(result: Result, packs: Path) -> str:
    return result.output.replace(str(packs.parent) + "/", "")


# --- day 4 -----------------------------------------------------------------------------


@pytest.fixture
def day3_pack(tmp_path: Path) -> Path:
    """A pack named acme that has everything up to day 3 and nothing of day 4."""
    root = tmp_path / "client_packs"
    shutil.copytree(
        ACME, root / "acme",
        ignore=shutil.ignore_patterns(
            "golden.jsonl", "thresholds.yaml", "rubric.md", "judge_calibration.jsonl",
            "retrieval.jsonl", "policies.yaml", "demo_cases.json",
        ),
    )  # fmt: skip
    (root / "acme" / "discovery.yaml").write_text(yaml.safe_dump(SIGNED), encoding="utf-8")
    return root


def _golden(packs: Path) -> list[str]:
    return (ACME / "golden.jsonl").read_text(encoding="utf-8").splitlines()


def _add_day4(packs: Path, lines: list[str] | None = None) -> None:
    pack = packs / "acme"
    (pack / "golden.jsonl").write_text("\n".join(lines or _golden(packs)) + "\n", encoding="utf-8")
    for name in ("thresholds.yaml", "rubric.md", "judge_calibration.jsonl"):
        shutil.copy(ACME / name, pack / name)


def test_day4_names_each_missing_file(day3_pack: Path) -> None:
    result = _validate(day3_pack, "day4", "acme")
    output = _plain(result, day3_pack)
    assert result.exit_code == 1
    assert "day4: golden.jsonl: 0 case(s) found, at least 20 needed" in output
    assert "day4: thresholds.yaml not found" in output
    assert "day4: rubric.md not found" in output
    assert "day4: judge_calibration.jsonl: no email scored by a person" in output


def test_day4_passes_with_a_golden_set_thresholds_and_calibration(day3_pack: Path) -> None:
    _add_day4(day3_pack)
    result = _validate(day3_pack, "day4", "acme")
    assert result.exit_code == 0, result.output


def test_day4_fails_with_fewer_than_twenty_cases(day3_pack: Path) -> None:
    _add_day4(day3_pack, _golden(day3_pack)[:19])
    result = _validate(day3_pack, "day4", "acme")
    assert result.exit_code == 1 and "19 case(s) found, at least 20 needed" in result.output


def test_day4_fails_on_a_case_for_a_contact_that_is_not_in_the_fixtures(day3_pack: Path) -> None:
    lines = _golden(day3_pack)
    first = json.loads(lines[0])
    lines[0] = json.dumps({**first, "contact_id": "acme-c-999"})
    _add_day4(day3_pack, lines)
    result = _validate(day3_pack, "day4", "acme")
    assert result.exit_code == 1
    assert f"case {first['id']} uses contact acme-c-999, which is not in the fixtures" in (
        result.output
    )


def test_day4_fails_on_a_malformed_thresholds_file(day3_pack: Path) -> None:
    _add_day4(day3_pack)
    (day3_pack / "acme" / "thresholds.yaml").write_text("tone_mean_min: 9\n", encoding="utf-8")
    result = _validate(day3_pack, "day4", "acme")
    assert result.exit_code == 1 and "thresholds.yaml" in result.output


def test_day4_still_needs_the_earlier_days(day3_pack: Path) -> None:
    _add_day4(day3_pack)
    (day3_pack / "acme" / "discovery.yaml").unlink()
    result = _validate(day3_pack, "day4", "acme")
    assert result.exit_code == 1 and "day1: discovery.yaml not found" in result.output


# --- day 5 -----------------------------------------------------------------------------


@pytest.fixture
def ready_pack(tmp_path: Path) -> Path:
    """The acme pack with a signed discovery, a fully ticked checklist and thresholds it meets."""
    root = tmp_path / "client_packs"
    shutil.copytree(ACME, root / "acme")
    pack = root / "acme"
    (pack / "discovery.yaml").write_text(yaml.safe_dump(SIGNED), encoding="utf-8")
    checklist = (REPO / "playbook" / "go-live-checklist.md").read_text(encoding="utf-8")
    (pack / "go_live.md").write_text(checklist.replace("- [ ]", "- [x]"), encoding="utf-8")
    (pack / "thresholds.yaml").write_text(yaml.safe_dump(MET), encoding="utf-8")
    return root


def test_day5_passes_when_policies_checklist_and_evals_are_all_in_order(ready_pack: Path) -> None:
    result = _validate(ready_pack, "day5", "acme")
    assert result.exit_code == 0, result.output
    assert "1 pack(s) checked at day5, 0 invalid" in result.output


def test_day5_fails_when_the_evals_miss_a_threshold_and_names_it(ready_pack: Path) -> None:
    (ready_pack / "acme" / "thresholds.yaml").write_text(yaml.safe_dump(UNMET), encoding="utf-8")
    result = _validate(ready_pack, "day5", "acme")
    assert result.exit_code == 1
    assert "day5: evals: tone_mean" in result.output and "below tone_mean_min 5.00" in result.output


def test_day5_names_every_box_left_unticked(ready_pack: Path) -> None:
    path = ready_pack / "acme" / "go_live.md"
    path.write_text(path.read_text().replace("- [x]", "- [ ]", 2), encoding="utf-8")
    result = _validate(ready_pack, "day5", "acme")
    assert result.exit_code == 1
    assert result.output.count("go_live.md: not ticked") == 2
    assert "The sponsor signed off the discovery" in result.output


def test_day5_fails_without_a_checklist_or_with_a_file_that_has_no_box(ready_pack: Path) -> None:
    path = ready_pack / "acme" / "go_live.md"
    path.write_text("Go live: ready.\n", encoding="utf-8")
    assert "go_live.md: no checklist box" in _validate(ready_pack, "day5", "acme").output
    path.unlink()
    assert "go_live.md not found" in _validate(ready_pack, "day5", "acme").output


def test_day5_needs_a_policies_file(ready_pack: Path) -> None:
    (ready_pack / "acme" / "policies.yaml").unlink()
    result = _validate(ready_pack, "day5", "acme")
    assert result.exit_code == 1 and "day5: policies.yaml not found" in result.output


def test_day5_does_not_measure_a_pack_that_fails_an_earlier_day(ready_pack: Path) -> None:
    (ready_pack / "acme" / "discovery.yaml").unlink()
    result = _validate(ready_pack, "day5", "acme")
    assert result.exit_code == 1
    assert "day5: evals: not run: fix days 1 to 4 first" in result.output


def test_day5_replays_whatever_the_environment_says_and_restores_it(
    ready_pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROUNDWORK_MODEL", "claude")
    monkeypatch.setenv("GROUNDWORK_RECORD", "1")
    monkeypatch.delenv("GROUNDWORK_EMBEDDING", raising=False)
    result = _validate(ready_pack, "day5", "acme")
    assert result.exit_code == 0, result.output
    assert os.environ["GROUNDWORK_MODEL"] == "claude"
    assert os.environ["GROUNDWORK_RECORD"] == "1"
    assert "GROUNDWORK_EMBEDDING" not in os.environ


def test_day5_writes_no_file_in_the_pack_or_in_traces(ready_pack: Path) -> None:
    def snapshot(root: Path) -> dict[Path, int]:
        return {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}

    packs_before, traces_before = snapshot(ready_pack), snapshot(REPO / "traces")
    _validate(ready_pack, "day5", "acme")
    assert snapshot(ready_pack) == packs_before
    assert snapshot(REPO / "traces") == traces_before
