from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from groundwork.entrypoints.api import app as api
from groundwork.entrypoints.cli import app

runner = CliRunner()
VALID = "crm: fixture\nmessaging: console\nvector_store: lancedb\nmodel: replay\n"


def _pack(root: Path, name: str, content: str) -> None:
    (root / name).mkdir()
    (root / name / "config.yaml").write_text(content)


def test_validate_packs_accepts_valid_pack(tmp_path: Path) -> None:
    _pack(tmp_path, "acme", VALID)
    result = runner.invoke(app, ["validate-packs", "--packs-dir", str(tmp_path)])
    assert result.exit_code == 0


def test_validate_packs_rejects_invalid_pack(tmp_path: Path) -> None:
    _pack(tmp_path, "acme", VALID + "extra: nope\n")
    result = runner.invoke(app, ["validate-packs", "--packs-dir", str(tmp_path)])
    assert result.exit_code == 1


def test_health_endpoint() -> None:
    assert TestClient(api).get("/health").json() == {"status": "ok"}
