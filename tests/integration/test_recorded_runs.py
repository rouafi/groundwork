"""The committed extraction runs, replayed offline from the real recordings in traces/.

AC1: replay reproduces the committed outputs byte for byte.
AC3 to AC5: grounding, injection, planted conflict and contradiction, through the
golden checks of each pack.
"""

import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from groundwork.entrypoints.cli import app

REPO = Path(__file__).resolve().parents[2]
PACKS = ("acme", "beta")
OUTPUTS = ("rules.proposed.yaml", "extraction_report.yaml")
GOLDEN_CHECKS = {"grounding", "injection", "conflicts", "contradictions"}
runner = CliRunner()


@pytest.fixture(autouse=True)
def offline_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GROUNDWORK_MODEL", "GROUNDWORK_RECORD"):
        monkeypatch.delenv(name, raising=False)

    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("network access during replay")

    monkeypatch.setattr(socket.socket, "connect", refuse)


def _replay(pack: str, out: Path) -> str:
    args = ["extract-rules", "--pack", pack, "--packs-dir", str(REPO / "client_packs")]
    args += ["--domains-dir", str(REPO / "domains"), "--traces-dir", str(REPO / "traces")]
    result = runner.invoke(app, [*args, "--out-dir", str(out)])
    assert result.exit_code == 0, result.output
    return result.output


@pytest.mark.parametrize("pack", PACKS)
def test_replay_reproduces_the_committed_outputs(pack: str, tmp_path: Path) -> None:
    _replay(pack, tmp_path)
    for name in OUTPUTS:
        committed = REPO / "client_packs" / pack / name
        assert (tmp_path / name).read_bytes() == committed.read_bytes(), name


@pytest.mark.parametrize("pack", PACKS)
def test_the_recorded_run_passes_every_golden_check(pack: str, tmp_path: Path) -> None:
    output = _replay(pack, tmp_path)
    checks = [line.split() for line in output.splitlines() if line.strip().startswith("golden")]
    assert {c[2].rstrip(":") for c in checks} == GOLDEN_CHECKS
    assert all(c[1] == "PASS" for c in checks), output
