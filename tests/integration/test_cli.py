import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner, Result

from groundwork.entrypoints.api import app as api
from groundwork.entrypoints.cli import app

REPO = Path(__file__).resolve().parents[2]
DOMAINS = REPO / "domains"
runner = CliRunner()


@pytest.fixture
def packs(tmp_path: Path) -> Path:
    """A copy of the shipped acme pack, safe to break."""
    root = tmp_path / "client_packs"
    shutil.copytree(REPO / "client_packs" / "acme", root / "acme")
    return root


def _validate(packs: Path, domains: Path = DOMAINS) -> Result:
    args = ["validate-packs", "--packs-dir", str(packs), "--domains-dir", str(domains)]
    return runner.invoke(app, args)


def _edit_json(path: Path, index: int, prop: str, value: str) -> None:
    items = json.loads(path.read_text())
    items[index]["properties"][prop] = value
    path.write_text(json.dumps(items))


def test_shipped_packs_are_valid() -> None:
    result = _validate(REPO / "client_packs")
    assert result.exit_code == 0, result.output
    assert "2 pack(s) checked, 0 invalid" in result.output


def test_valid_pack_is_accepted(packs: Path) -> None:
    result = _validate(packs)
    assert result.exit_code == 0, result.output


def test_deal_with_missing_contact_names_pack_kind_and_ids(packs: Path) -> None:
    deals = packs / "acme" / "fixtures" / "hubspot" / "deals.json"
    items = json.loads(deals.read_text())
    items[2]["associations"]["contacts"]["results"][0]["id"] = "acme-c-99"
    deals.write_text(json.dumps(items))
    result = _validate(packs)
    assert result.exit_code == 1
    assert f"{packs / 'acme'}: deal acme-d-3 references missing contact acme-c-99" in result.output
    assert "1 pack(s) checked, 1 invalid" in result.output


def test_value_outside_domain_vocabulary_is_rejected(packs: Path) -> None:
    _edit_json(packs / "acme" / "fixtures" / "hubspot" / "contacts.json", 0, "persona", "ceo")
    result = _validate(packs)
    assert result.exit_code == 1
    assert "contact acme-c-1 has persona 'ceo', not in the domain vocabulary" in result.output


def test_malformed_fixture_names_the_file(packs: Path) -> None:
    _edit_json(packs / "acme" / "fixtures" / "hubspot" / "products.json", 0, "price", "free")
    result = _validate(packs)
    assert result.exit_code == 1
    assert "products.json: product acme-p-1: price: " in result.output


def test_unknown_domain_is_rejected(packs: Path, tmp_path: Path) -> None:
    result = _validate(packs, domains=tmp_path / "no-domains")
    assert result.exit_code == 1
    assert "acme: domain 'comms' not found" in result.output


def test_unknown_crm_adapter_lists_valid_names(packs: Path) -> None:
    config = packs / "acme" / "config.yaml"
    config.write_text(config.read_text().replace("crm: fixture", "crm: salesforce"))
    result = _validate(packs)
    assert result.exit_code == 1
    assert "unknown crm adapter 'salesforce' (valid: fixture)" in result.output


def test_pack_without_config_is_reported(packs: Path) -> None:
    (packs / "draft").mkdir()
    result = _validate(packs)
    assert result.exit_code == 1
    assert "config.yaml: file not found" in result.output
    assert "2 pack(s) checked, 1 invalid" in result.output


def test_invalid_config_is_rejected(packs: Path) -> None:
    config = packs / "acme" / "config.yaml"
    config.write_text(config.read_text() + "extra: nope\n")
    result = _validate(packs)
    assert result.exit_code == 1
    assert "config.yaml: extra: Extra inputs are not permitted" in result.output


def test_health_endpoint() -> None:
    assert TestClient(api).get("/health").json() == {"status": "ok"}
