import json
from pathlib import Path

import pytest

from groundwork.core.domain.errors import PackError
from groundwork.core.services.packs import DEMO_FILE, load_demo_cases

ROOT = Path(__file__).resolve().parents[2]
CASE = {
    "case_id": "demo-1",
    "title": "A case",
    "contact_id": "acme-c-1",
    "channel": "external",
    "draft": "Hi.",
}


def _pack(tmp_path: Path, content: object) -> Path:
    text = content if isinstance(content, str) else json.dumps(content)
    (tmp_path / DEMO_FILE).write_text(text, encoding="utf-8")
    return tmp_path


def test_a_pack_without_demo_cases_has_none(tmp_path: Path) -> None:
    assert load_demo_cases(tmp_path) == ()


def test_a_case_is_a_request_named_after_its_case_id_with_the_real_prompt_by_default(
    tmp_path: Path,
) -> None:
    (case,) = load_demo_cases(_pack(tmp_path, [CASE]))
    assert case.passthrough is False
    assert case.request.id == "demo-1"
    assert (case.request.contact_id, case.request.channel, case.request.draft) == (
        "acme-c-1", "external", "Hi.",
    )  # fmt: skip


@pytest.mark.parametrize(
    ("content", "needle"),
    [
        ("not json", "not a JSON list"),
        ({"case_id": "x"}, "not a JSON list"),
        ([{**CASE, "channel": "any"}], "channel"),
        ([{**CASE, "case_id": "../x"}], "case_id"),
        ([{**CASE, "extra": 1}], "extra"),
        ([CASE, CASE], "unique"),
    ],
)
def test_a_bad_demo_file_names_the_file_and_the_problem(
    tmp_path: Path, content: object, needle: str
) -> None:
    with pytest.raises(PackError) as error:
        load_demo_cases(_pack(tmp_path, content))
    assert "demo_cases.json" in str(error.value) and needle in str(error.value)


@pytest.mark.parametrize("pack", ["acme", "beta"])
def test_the_shipped_demo_has_three_cases_with_both_channels_and_one_passthrough(pack: str) -> None:
    cases = load_demo_cases(ROOT / "client_packs" / pack)
    assert len(cases) == 3
    assert {c.channel for c in cases} == {"internal", "external"}
    passthrough = [c for c in cases if c.passthrough]
    assert len(passthrough) == 1 and passthrough[0].channel == "external"
