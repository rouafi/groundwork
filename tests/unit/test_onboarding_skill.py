"""The client-onboarding skill is a file the playbook relies on: keep it honest."""

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / ".claude" / "skills" / "client-onboarding" / "SKILL.md"

# A skill that tells the model to write one of these would do a human's job: the sponsor's
# sign-off, a rule approval, a ticked go-live box.
HUMAN_ONLY_WRITES = [
    r"signed_off\s*:\s*true",
    r"status\s*:\s*[\"']?signed_off",
    r"status\s*:\s*[\"']?approved",
    r"signed_off_by\s*:\s*\S",
    r"- \[[xX]\]",
]


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _front_matter() -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", _text(), re.DOTALL)
    assert match, "SKILL.md must start with a front matter block"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def test_the_front_matter_names_the_skill_and_says_when_to_use_it() -> None:
    meta = _front_matter()
    assert meta["name"] == SKILL.parent.name == "client-onboarding"
    assert isinstance(meta["description"], str) and len(meta["description"]) > 40


def test_every_linked_file_exists() -> None:
    links = re.findall(r"\]\(([^)#]+)\)", _text())
    assert links, "the skill should link the templates it relies on"
    missing = [link for link in links if not (SKILL.parent / link).resolve().exists()]
    assert missing == []


def test_every_repo_path_in_code_spans_exists() -> None:
    paths = re.findall(r"`((?:docs|playbook|domains|src)/[^`<>\s]+)`", _text())
    assert [p for p in paths if not (REPO / p).exists()] == []


def test_every_groundwork_command_it_names_exists() -> None:
    from groundwork.entrypoints.cli import app

    names = {c.name or c.callback.__name__.replace("_", "-") for c in app.registered_commands}  # type: ignore[union-attr]
    used = set(re.findall(r"groundwork ([a-z][a-z-]+)", _text()))
    assert used and used <= names, used - names


@pytest.mark.parametrize("pattern", HUMAN_ONLY_WRITES)
def test_the_skill_never_tells_the_model_to_do_a_human_only_action(pattern: str) -> None:
    assert re.search(pattern, _text()) is None


def test_the_skill_states_the_human_only_actions_and_the_stage_check() -> None:
    text = _text()
    assert "## Human-only actions" in text
    for action in ("sign-off", "approval of each rule", "ticking each box"):
        assert action in text
    assert "validate-packs --pack <client> --stage dayN" in text


@pytest.mark.parametrize(
    "bad",
    [
        "Then set `signed_off: true` in discovery.yaml.",
        "Write status: signed_off once the client agrees.",
        "Set status: approved on each rule.",
        "signed_off_by: the FDE",
        "- [x] Every approved rule was read",
    ],
)
def test_the_scan_catches_the_instructions_it_exists_to_forbid(bad: str) -> None:
    assert any(re.search(p, bad) for p in HUMAN_ONLY_WRITES)
