"""The results block of the README is copied from evals/report.md, never typed."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "readme_results", REPO / "scripts/readme_results.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rr = _load()

REPORT = """# Evals report

## Summary

| Pack | Cases | Result |
|---|---|---|
| one | 20 | PASS |
| two | 20 | FAIL (tone_mean) |

## one

Result: **PASS**

### Thresholds

| Scorer | Value |
|---|---|
| tone_mean | 4.5 |

### Before and after the agent

| | Raw draft | Harmonized |
|---|---|---|
| False claims | 7 | 0 |

### Cases

| Case |
|---|
| one-001 |

## two

### Before and after the agent

| | Raw draft | Harmonized |
|---|---|---|
| False claims | 3 | 1 |

### Cases

| Case |
|---|
| two-001 |
"""
README = f"# Title\n\nintro\n\n{rr.START}\nold\n{rr.END}\n\nafter\n"


def test_the_block_holds_the_summary_and_each_packs_before_and_after_tables() -> None:
    block = rr.build_block(REPORT)
    assert "| one | 20 | PASS |" in block and "| two | 20 | FAIL (tone_mean) |" in block
    assert "**one**, before and after the agent:" in block
    assert "| False claims | 7 | 0 |" in block and "| False claims | 3 | 1 |" in block
    assert "one-001" not in block and "| tone_mean | 4.5 |" not in block


def test_the_block_says_which_packs_are_below_their_thresholds_only_when_one_is() -> None:
    assert "Packs marked FAIL are below at least one" in rr.build_block(REPORT)
    passing = REPORT.replace("FAIL (tone_mean)", "PASS")
    assert "Every pack meets its thresholds." in rr.build_block(passing)


def test_inject_replaces_only_what_is_between_the_markers_and_is_idempotent() -> None:
    once = rr.inject(README, "NEW")
    assert once == f"# Title\n\nintro\n\n{rr.START}\nNEW\n{rr.END}\n\nafter\n"
    assert rr.inject(once, "NEW") == once


@pytest.mark.parametrize(
    "readme",
    ["no markers", f"{rr.START} only", f"{rr.END}\n{rr.START}", f"{rr.START}{rr.END}{rr.START}"],
)
def test_inject_refuses_a_readme_without_exactly_one_ordered_pair_of_markers(readme: str) -> None:
    with pytest.raises(rr.ResultsError, match="exactly one"):
        rr.inject(readme, "x")


def test_a_report_without_a_summary_or_without_packs_is_an_error() -> None:
    with pytest.raises(rr.ResultsError, match="Summary"):
        rr.build_block("# Evals report\n")
    with pytest.raises(rr.ResultsError, match="no pack section"):
        rr.build_block("## Summary\n\n| a |\n")


def _files(tmp_path: Path) -> tuple[Path, Path]:
    report, readme = tmp_path / "report.md", tmp_path / "README.md"
    report.write_text(REPORT, encoding="utf-8")
    readme.write_text(README, encoding="utf-8")
    return report, readme


def test_check_fails_on_a_stale_block_without_touching_the_readme(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report, readme = _files(tmp_path)
    assert rr.main(["--check", "--report", str(report), "--readme", str(readme)]) == 1
    assert "stale" in capsys.readouterr().err
    assert readme.read_text(encoding="utf-8") == README


def test_writing_makes_the_check_pass_and_a_hand_edit_of_a_number_makes_it_fail(
    tmp_path: Path,
) -> None:
    report, readme = _files(tmp_path)
    args = ["--report", str(report), "--readme", str(readme)]
    assert rr.main(args) == 0
    assert rr.main(["--check", *args]) == 0
    readme.write_text(
        readme.read_text().replace("| False claims | 7 | 0 |", "| False claims | 7 | 9 |")
    )
    assert rr.main(["--check", *args]) == 1


def test_the_check_fails_when_the_report_changes(tmp_path: Path) -> None:
    report, readme = _files(tmp_path)
    args = ["--report", str(report), "--readme", str(readme)]
    rr.main(args)
    report.write_text(REPORT.replace("| False claims | 3 | 1 |", "| False claims | 3 | 2 |"))
    assert rr.main(["--check", *args]) == 1


def test_a_missing_file_is_an_error_not_a_crash(tmp_path: Path) -> None:
    assert rr.main(["--report", str(tmp_path / "nope.md"), "--readme", str(tmp_path / "r.md")]) == 1


def test_the_committed_readme_is_in_step_with_the_committed_report() -> None:
    args = [
        "--check",
        "--report",
        str(REPO / "evals/report.md"),
        "--readme",
        str(REPO / "README.md"),
    ]
    assert rr.main(args) == 0
