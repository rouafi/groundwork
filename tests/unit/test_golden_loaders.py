import json
from pathlib import Path

import pytest

from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.core.domain.errors import PackError
from groundwork.core.services.integrity import golden_case_problems
from groundwork.core.services.packs import (
    GOLDEN_FILE,
    load_golden,
    load_rubric,
    load_thresholds,
)

ACME = Path(__file__).resolve().parents[2] / "client_packs" / "acme"
CASE = {"id": "acme-001", "contact_id": "acme-c-1", "channel": "external",
        "draft": "Hi.", "expected_route": "approval"}  # fmt: skip


def _golden(tmp_path: Path, *cases: dict[str, object]) -> Path:
    (tmp_path / GOLDEN_FILE).write_text("\n".join(json.dumps(c) for c in cases) + "\n")
    return tmp_path


def test_a_pack_without_eval_files_has_none(tmp_path: Path) -> None:
    assert load_golden(tmp_path) == ()
    assert load_thresholds(tmp_path) is None
    assert load_rubric(tmp_path) is None


def test_the_cases_are_read_one_per_line(tmp_path: Path) -> None:
    cases = load_golden(_golden(tmp_path, CASE, {**CASE, "id": "acme-002"}))
    assert [c.id for c in cases] == ["acme-001", "acme-002"]


def test_a_bad_line_names_the_file_and_the_line(tmp_path: Path) -> None:
    pack = _golden(tmp_path, CASE, {**CASE, "channel": "any"})
    with pytest.raises(PackError, match=r"golden\.jsonl:2"):
        load_golden(pack)


def test_duplicate_case_ids_are_rejected_by_name(tmp_path: Path) -> None:
    with pytest.raises(PackError, match=r"duplicate case ids \['acme-001'\]"):
        load_golden(_golden(tmp_path, CASE, CASE))


def test_thresholds_and_rubric_load_from_the_pack(tmp_path: Path) -> None:
    (tmp_path / "thresholds.yaml").write_text("tone_mean_min: 3.5\n")
    (tmp_path / "rubric.md").write_text("5 means warm and exact.\n")
    thresholds = load_thresholds(tmp_path)
    assert thresholds is not None and thresholds.tone_mean_min == 3.5
    assert thresholds.fact_false_claims == 0
    assert load_rubric(tmp_path) == "5 means warm and exact.\n"


def test_a_threshold_file_with_an_unknown_key_names_the_file(tmp_path: Path) -> None:
    (tmp_path / "thresholds.yaml").write_text("tone_mean: 4\n")
    with pytest.raises(PackError, match=r"thresholds\.yaml"):
        load_thresholds(tmp_path)


def test_a_golden_set_needs_a_known_contact_thresholds_and_a_rubric(tmp_path: Path) -> None:
    crm = FixtureCrm(ACME / "fixtures" / "hubspot")
    cases = load_golden(
        _golden(tmp_path, CASE, {**CASE, "id": "acme-002", "contact_id": "acme-c-404"})
    )
    problems = golden_case_problems(
        cases, crm, has_thresholds=False, has_rubric=False, has_calibration=False
    )
    assert problems == [
        "golden case acme-002: unknown contact 'acme-c-404'",
        "golden.jsonl has cases but thresholds.yaml is missing",
        "golden.jsonl has cases but rubric.md is missing",
        "golden.jsonl has cases but judge_calibration.jsonl is missing",
    ]
    assert golden_case_problems(cases[:1], crm, True, True, True) == []
    assert golden_case_problems((), crm, False, False, False) == []
