"""`groundwork new-pack` in a temporary folder: no client pack is ever created in the repository."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner, Result

from groundwork.core.domain.discovery import DiscoveryDoc
from groundwork.core.services.packs import load_pack_config
from groundwork.entrypoints.cli import app

REPO = Path(__file__).resolve().parents[2]
runner = CliRunner()


@pytest.fixture
def packs(tmp_path: Path) -> Path:
    return tmp_path / "client_packs"


def _new_pack(packs: Path, client: str = "gamma", *extra: str) -> Result:
    args = [
        "new-pack", client,
        "--packs-dir", str(packs),
        "--domains-dir", str(REPO / "domains"),
        "--playbook-dir", str(REPO / "playbook"),
        *extra,
    ]  # fmt: skip
    return runner.invoke(app, args)


def test_new_pack_creates_the_skeleton_and_says_what_to_do_next(packs: Path) -> None:
    result = _new_pack(packs)
    assert result.exit_code == 0, result.output
    pack = packs / "gamma"
    assert sorted(p.name for p in pack.iterdir()) == [
        "config.yaml", "discovery.yaml", "fixtures", "go_live.md", "interviews",
    ]  # fmt: skip
    assert (pack / "fixtures" / "hubspot").is_dir()
    assert "validate-packs --pack gamma --stage day1" in result.output
    assert "recorded by a person" in result.output


def test_the_new_config_is_valid_and_names_the_client_and_the_domain(packs: Path) -> None:
    _new_pack(packs, "gamma", "--domain", "comms")
    config = load_pack_config(packs / "gamma")
    assert config.domain == "comms" and config.internal_recipient == "handoffs@gamma.example"
    assert "__" not in (packs / "gamma" / "config.yaml").read_text()


def test_the_new_discovery_names_the_client_is_a_draft_and_is_not_valid_yet(packs: Path) -> None:
    _new_pack(packs)
    data = yaml.safe_load((packs / "gamma" / "discovery.yaml").read_text())
    assert data["client"] == "gamma" and data["status"] == "draft" and data["signed_off_by"] is None
    with pytest.raises(ValidationError):
        DiscoveryDoc.model_validate(data)


def test_the_new_go_live_checklist_has_no_ticked_box(packs: Path) -> None:
    _new_pack(packs)
    text = (packs / "gamma" / "go_live.md").read_text()
    assert "- [ ]" in text and "- [x]" not in text.lower()


def test_the_skeleton_is_data_only(packs: Path) -> None:
    _new_pack(packs)
    suffixes = {p.suffix for p in (packs / "gamma").rglob("*") if p.is_file()}
    assert suffixes <= {".yaml", ".md"}


def test_new_pack_never_overwrites_a_pack(packs: Path) -> None:
    assert _new_pack(packs).exit_code == 0
    keep = packs / "gamma" / "discovery.yaml"
    keep.write_text("client: gamma\n# edited by a person\n")
    result = _new_pack(packs)
    assert result.exit_code == 1 and "already exists" in result.output
    assert "edited by a person" in keep.read_text()


@pytest.mark.parametrize("name", ["Gamma", "../gamma", "gamma corp", "1gamma", "gamma_corp"])
def test_new_pack_refuses_a_name_that_is_not_a_folder_safe_slug(packs: Path, name: str) -> None:
    result = _new_pack(packs, name)
    assert result.exit_code == 1 and "invalid client name" in result.output
    assert not packs.exists() or not any(packs.iterdir())


def test_new_pack_refuses_an_unknown_domain_and_creates_nothing(packs: Path) -> None:
    result = _new_pack(packs, "gamma", "--domain", "nonesuch")
    assert result.exit_code == 1 and "domain 'nonesuch' not found" in result.output
    assert not (packs / "gamma").exists()


def test_a_missing_template_is_reported_and_leaves_no_half_pack(
    packs: Path, tmp_path: Path
) -> None:
    playbook = tmp_path / "playbook"
    playbook.mkdir()
    (playbook / "config.template.yaml").write_text("domain: __DOMAIN__\n")
    args = ["new-pack", "gamma", "--packs-dir", str(packs), "--domains-dir", str(REPO / "domains"),
            "--playbook-dir", str(playbook)]  # fmt: skip
    result = runner.invoke(app, args)
    assert result.exit_code == 1 and "playbook template not found" in result.output
    assert not (packs / "gamma").exists()
    assert not list(packs.glob(".new-*"))


def test_the_other_packs_are_untouched(packs: Path) -> None:
    (packs / "acme").mkdir(parents=True)
    (packs / "acme" / "config.yaml").write_text("keep: me\n")
    _new_pack(packs)
    assert (packs / "acme" / "config.yaml").read_text() == "keep: me\n"
