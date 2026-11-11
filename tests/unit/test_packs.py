from pathlib import Path

import pytest

from groundwork.core.domain.errors import PackError
from groundwork.core.services.packs import load_domain_pack, load_pack_config

DOMAIN_YAML = """\
segments: [smb, enterprise]
personas: [economic-buyer]
channels: [internal, external]
defaults: {tone: formal}
"""
CONFIG_YAML = """\
crm: fixture
messaging: console
vector_store: lancedb
model: replay
domain: comms
"""


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_loads_domain_pack(tmp_path: Path) -> None:
    _write(tmp_path / "comms" / "domain.yaml", DOMAIN_YAML)
    domain = load_domain_pack(tmp_path, "comms")
    assert domain.segments == ("smb", "enterprise")
    assert domain.defaults.tone == "formal"


def test_missing_domain_names_the_folder(tmp_path: Path) -> None:
    with pytest.raises(PackError, match=r"domain 'sales' not found: .*sales does not exist"):
        load_domain_pack(tmp_path, "sales")


def test_missing_domain_file_is_reported(tmp_path: Path) -> None:
    (tmp_path / "comms").mkdir()
    with pytest.raises(PackError, match=r"domain\.yaml: file not found"):
        load_domain_pack(tmp_path, "comms")


def test_duplicate_vocabulary_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "comms" / "domain.yaml", DOMAIN_YAML.replace("[smb,", "[smb, smb,"))
    with pytest.raises(PackError, match=r"segments: .*duplicate values: smb"):
        load_domain_pack(tmp_path, "comms")


def test_empty_vocabulary_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path / "comms" / "domain.yaml", DOMAIN_YAML.replace("[economic-buyer]", "[]"))
    with pytest.raises(PackError, match=r"personas"):
        load_domain_pack(tmp_path, "comms")


def test_loads_pack_config(tmp_path: Path) -> None:
    _write(tmp_path / "config.yaml", CONFIG_YAML)
    assert load_pack_config(tmp_path).domain == "comms"


def test_invalid_config_names_file_and_field(tmp_path: Path) -> None:
    _write(tmp_path / "config.yaml", CONFIG_YAML.replace("domain: comms\n", ""))
    with pytest.raises(PackError, match=r"config\.yaml: domain: Field required"):
        load_pack_config(tmp_path)


def test_invalid_yaml_is_reported(tmp_path: Path) -> None:
    _write(tmp_path / "config.yaml", "crm: [unclosed\n")
    with pytest.raises(PackError, match=r"config\.yaml: invalid YAML"):
        load_pack_config(tmp_path)


def test_non_mapping_yaml_is_reported(tmp_path: Path) -> None:
    _write(tmp_path / "config.yaml", "- just\n- a list\n")
    with pytest.raises(PackError, match=r"config\.yaml: <root>"):
        load_pack_config(tmp_path)
