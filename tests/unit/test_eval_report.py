import json
import re
from pathlib import Path

from groundwork.core.domain.evals import PackResult
from groundwork.core.services.evals.report import (
    HEADER,
    RESULTS_DIR,
    render_report,
    report_drift,
    result_json,
    write_outputs,
)
from groundwork.core.services.evals.runner import run_pack
from tests.evals_support import CaseAgent, EvalModel, case, deps, email


def _result(tone: int = 5, pack_cases: int = 2) -> PackResult:
    cases = [case(f"a-{i}", tags=["realistic"]) for i in range(1, pack_cases + 1)]
    return run_pack(deps(cases, CaseAgent({}, email()), EvalModel(tone=tone)))


def test_the_report_starts_with_its_header_and_says_the_data_is_synthetic() -> None:
    text = render_report([_result()])
    assert text.startswith("# Evals report\n")
    assert HEADER in text and "synthetic" in text and text.endswith("\n")


def test_the_same_results_give_the_same_bytes_and_no_timestamp() -> None:
    first, second = render_report([_result()]), render_report([_result()])
    assert first == second
    assert not re.search(r"\d{4}-\d{2}-\d{2}", first)
    assert result_json(_result()) == result_json(_result())


def test_the_report_shows_thresholds_before_and_after_and_every_case_in_order() -> None:
    text = render_report([_result(pack_cases=3)])
    for heading in (
        "## acme",
        "### Thresholds",
        "### Before and after the agent",
        "### Cases",
        "### Judge calibration",
    ):
        assert heading in text
    assert "| False claims |" in text and "| Tone, mean from 1 to 5 |" in text
    assert text.index("| a-1 |") < text.index("| a-2 |") < text.index("| a-3 |")
    assert "| tone_mean | 5 | 4 | pass |" in text


def test_a_failing_pack_is_flagged_in_the_summary_and_its_section() -> None:
    result = run_pack(deps([case("a-1", expected_route="blocked")], CaseAgent({}), EvalModel()))
    text = render_report([result])
    assert "| acme | 1 | FAIL (routing_accuracy) |" in text
    assert "**blocked / approval**" in text and "| routing_accuracy | 0 | 1 | FAIL |" in text


def test_the_json_is_sorted_and_round_trips_the_numbers() -> None:
    data = json.loads(result_json(_result()))
    assert list(data) == sorted(data)
    assert data["pack"] == "acme" and data["metrics"]["cases"] == 2
    assert data["metrics"]["tone_mean"] == 5.0


def test_written_files_match_a_regeneration_and_any_edit_is_drift(tmp_path: Path) -> None:
    results = [_result()]
    written = write_outputs(results, tmp_path)
    assert [p.name for p in written] == ["report.md", "acme.json"]
    assert report_drift(results, tmp_path) == []

    report = tmp_path / "report.md"
    report.write_text(report.read_text().replace("| 5 |", "| 4 |", 1))
    assert report_drift(results, tmp_path) == [f"{report} differs from a replay regeneration"]

    write_outputs(results, tmp_path)
    (tmp_path / RESULTS_DIR / "acme.json").unlink()
    assert report_drift(results, tmp_path) == [f"{tmp_path / RESULTS_DIR / 'acme.json'} is missing"]


def test_a_different_result_is_drift_against_the_committed_report(tmp_path: Path) -> None:
    write_outputs([_result(tone=5)], tmp_path)
    problems = report_drift([_result(tone=4)], tmp_path)
    assert len(problems) == 2 and all("differs" in p for p in problems)
