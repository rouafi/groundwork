"""validate-packs --stage on a pack built day by day in a temporary folder.

The pack is scaffolded by `new-pack`; its facts, interviews and rules are copied from the
shipped acme pack inside the temporary folder, so no client pack is ever created in the repo.
"""

import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner, Result

from groundwork.entrypoints.cli import app

REPO = Path(__file__).resolve().parents[2]
ACME = REPO / "client_packs" / "acme"
runner = CliRunner()

DISCOVERY = {
    "sponsor": "Head of customer success",
    "use_case": "Harmonize customer emails so every team states the same prices and promises.",
    "users": ["account managers"],
    "channels": ["internal", "external"],
    "systems": [{"name": "HubSpot", "role": "contacts, deals and products"}],
    "success_metric": {"name": "corrections", "baseline": "30%", "target": "10%"},
    "risks": ["a wrong price reaches a customer"],
}


@pytest.fixture
def packs(tmp_path: Path) -> Path:
    root = tmp_path / "client_packs"
    args = ["new-pack", "gamma", "--packs-dir", str(root), "--domains-dir", str(REPO / "domains"),
            "--playbook-dir", str(REPO / "playbook")]  # fmt: skip
    assert runner.invoke(app, args).exit_code == 0
    return root


def _validate(packs: Path, stage: str, *extra: str) -> Result:
    args = ["validate-packs", "--packs-dir", str(packs), "--domains-dir", str(REPO / "domains"),
            "--stage", stage, *extra]  # fmt: skip
    return runner.invoke(app, args)


def _discovery(packs: Path, **changes: object) -> Path:
    path = packs / "gamma" / "discovery.yaml"
    path.write_text(yaml.safe_dump({"client": "gamma", **DISCOVERY, **changes}), encoding="utf-8")
    return path


def _sign(packs: Path) -> None:
    _discovery(packs, status="signed_off", signed_off_by="Ana Silva, head of customer success")


def _facts(packs: Path) -> None:
    shutil.copytree(ACME / "fixtures", packs / "gamma" / "fixtures", dirs_exist_ok=True)


def _know_how(packs: Path) -> None:
    shutil.copytree(ACME / "interviews", packs / "gamma" / "interviews", dirs_exist_ok=True)
    shutil.copy(ACME / "rules.yaml", packs / "gamma" / "rules.yaml")


# --- day 1 -----------------------------------------------------------------------------


def test_the_skeleton_fails_day1_and_names_every_missing_field(packs: Path) -> None:
    result = _validate(packs, "day1")
    assert result.exit_code == 1
    output = result.output.replace(str(packs.parent) + "/", "")
    fields = [
        "sponsor", "use_case", "users", "channels", "systems", "risks",
        "success_metric.name", "success_metric.baseline", "success_metric.target",
    ]  # fmt: skip
    for field in fields:
        assert f"client_packs/gamma: day1: discovery.yaml: {field}:" in output, field
    assert "1 invalid" in result.output


def test_filling_and_signing_the_discovery_makes_day1_pass_and_breaking_it_fails_again(
    packs: Path,
) -> None:
    _sign(packs)
    passed = _validate(packs, "day1")
    assert passed.exit_code == 0, passed.output
    assert "1 pack(s) checked at day1, 0 invalid" in passed.output

    _discovery(packs, status="signed_off", signed_off_by="Ana Silva", sponsor="")
    broken = _validate(packs, "day1")
    assert broken.exit_code == 1 and "discovery.yaml: sponsor:" in broken.output


def test_a_filled_but_unsigned_discovery_fails_day1_and_says_a_person_signs(packs: Path) -> None:
    _discovery(packs)
    result = _validate(packs, "day1")
    assert result.exit_code == 1
    assert "status is draft: the sponsor signs it off" in result.output


def test_a_discovery_for_another_client_fails_day1(packs: Path) -> None:
    path = _discovery(packs, status="signed_off", signed_off_by="Ana")
    path.write_text(path.read_text().replace("client: gamma", "client: delta"))
    result = _validate(packs, "day1")
    assert (
        result.exit_code == 1 and "client 'delta' is not the pack's name 'gamma'" in result.output
    )


def test_a_missing_or_unreadable_discovery_is_reported(packs: Path) -> None:
    (packs / "gamma" / "discovery.yaml").unlink()
    assert (
        "discovery.yaml not found (groundwork new-pack creates it)"
        in _validate(packs, "day1").output
    )
    (packs / "gamma" / "discovery.yaml").write_text("client: [unclosed\n")
    assert "not valid YAML" in _validate(packs, "day1").output


# --- day 2 -----------------------------------------------------------------------------


def test_day2_fails_while_the_fixtures_are_missing_and_passes_once_they_load(packs: Path) -> None:
    _sign(packs)
    empty = _validate(packs, "day2")
    assert empty.exit_code == 1 and "day2:" in empty.output
    _facts(packs)
    assert _validate(packs, "day2").exit_code == 0


def test_day2_fails_on_an_inconsistent_fixture_naming_the_object(packs: Path) -> None:
    _sign(packs)
    _facts(packs)
    deals = packs / "gamma" / "fixtures" / "hubspot" / "deals.json"
    deals.write_text(deals.read_text().replace("acme-c-1", "acme-c-99", 1))
    result = _validate(packs, "day2")
    assert result.exit_code == 1 and "references missing contact acme-c-99" in result.output


def test_day2_fails_on_an_invalid_config(packs: Path) -> None:
    _sign(packs)
    _facts(packs)
    config = packs / "gamma" / "config.yaml"
    config.write_text(config.read_text().replace("domain: comms", "domain: nonesuch"))
    result = _validate(packs, "day2")
    assert result.exit_code == 1 and "domain 'nonesuch' not found" in result.output


# --- day 3 -----------------------------------------------------------------------------


def test_day3_needs_three_interviews_and_an_approved_rule(packs: Path) -> None:
    _sign(packs)
    _facts(packs)
    bare = _validate(packs, "day3")
    assert bare.exit_code == 1
    assert "interviews: 0 found, at least 3 needed" in bare.output
    assert "no approved rule" in bare.output

    _know_how(packs)
    done = _validate(packs, "day3")
    assert done.exit_code == 0, done.output


def test_day3_fails_when_a_rule_quote_is_not_in_its_interview(packs: Path) -> None:
    _sign(packs)
    _facts(packs)
    _know_how(packs)
    interview = next((packs / "gamma" / "interviews").glob("*-1.md"))
    interview.write_text(interview.read_text().replace("discount", "rebate"))
    result = _validate(packs, "day3")
    assert result.exit_code == 1 and "cites a quote absent from" in result.output


def test_day3_fails_with_two_interviews(packs: Path) -> None:
    _sign(packs)
    _facts(packs)
    _know_how(packs)
    next((packs / "gamma" / "interviews").glob("*-3.md")).unlink()
    result = _validate(packs, "day3")
    assert result.exit_code == 1 and "interviews: 2 found, at least 3 needed" in result.output


# --- stages are cumulative -------------------------------------------------------------


def test_a_later_stage_still_needs_the_earlier_days(packs: Path) -> None:
    _facts(packs)
    _know_how(packs)
    result = _validate(packs, "day3")
    assert result.exit_code == 1
    assert "day1: discovery.yaml: sponsor:" in result.output.replace(str(packs.parent) + "/", "")


def test_a_stage_reports_the_problems_of_each_day_with_its_day(packs: Path) -> None:
    output = _validate(packs, "day3").output.replace(str(packs.parent) + "/", "")
    assert "day1:" in output and "day2:" in output and "day3:" in output


# --- selecting packs -------------------------------------------------------------------


def test_pack_selects_one_pack_and_an_unknown_one_is_an_error(packs: Path) -> None:
    other = packs / "delta"
    shutil.copytree(packs / "gamma", other)
    assert "1 pack(s) checked at day1" in _validate(packs, "day1", "--pack", "gamma").output
    missing = _validate(packs, "day1", "--pack", "nonesuch")
    assert missing.exit_code == 1 and "no such pack" in missing.output


def test_a_stage_never_changes_a_file(packs: Path) -> None:
    before = {p: p.read_bytes() for p in packs.rglob("*") if p.is_file()}
    _validate(packs, "day3")
    assert {p: p.read_bytes() for p in packs.rglob("*") if p.is_file()} == before


def test_validate_packs_without_a_stage_still_checks_the_shipped_packs() -> None:
    args = [
        "validate-packs",
        "--packs-dir",
        str(REPO / "client_packs"),
        "--domains-dir",
        str(REPO / "domains"),
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0 and "2 pack(s) checked, 0 invalid" in result.output
