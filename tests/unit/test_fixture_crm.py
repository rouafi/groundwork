import json
import shutil
from pathlib import Path

import pytest

from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.core.domain.errors import PackError

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "crm_sample"


@pytest.fixture
def fixtures(tmp_path: Path) -> Path:
    target = tmp_path / "hubspot"
    shutil.copytree(SAMPLE, target)
    return target


def test_loads_sample(fixtures: Path) -> None:
    crm = FixtureCrm(fixtures)
    assert crm.get_contact("c_2").notes == "Prefers short emails."


def test_missing_file_names_the_file(fixtures: Path) -> None:
    (fixtures / "deals.json").unlink()
    with pytest.raises(PackError, match=r"deals\.json: file not found"):
        FixtureCrm(fixtures)


def test_invalid_json_names_the_file(fixtures: Path) -> None:
    (fixtures / "products.json").write_text("[{")
    with pytest.raises(PackError, match=r"products\.json: invalid JSON"):
        FixtureCrm(fixtures)


def test_non_array_names_the_file(fixtures: Path) -> None:
    (fixtures / "companies.json").write_text("{}")
    with pytest.raises(PackError, match=r"companies\.json: expected a JSON array"):
        FixtureCrm(fixtures)


def test_malformed_object_names_file_kind_and_id(fixtures: Path) -> None:
    path = fixtures / "contacts.json"
    contacts = json.loads(path.read_text())
    contacts[1]["properties"]["email"] = "nope"
    path.write_text(json.dumps(contacts))
    with pytest.raises(PackError, match=r"contacts\.json: contact c_2: email: "):
        FixtureCrm(fixtures)


def test_duplicate_id_is_rejected(fixtures: Path) -> None:
    path = fixtures / "companies.json"
    companies = json.loads(path.read_text())
    path.write_text(json.dumps([*companies, companies[0]]))
    with pytest.raises(PackError, match=r"companies\.json: duplicate id co_1"):
        FixtureCrm(fixtures)
