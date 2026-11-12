"""extract-rules end to end on replay, from recordings made in a temporary trace directory.

The recordings come from a scripted stub through RecordingModel, so this suite runs
before any real recording exists. Real recordings are covered by test_recorded_runs.py.
"""

import shutil
import socket
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from groundwork.adapters.model.recording import Recordings, specs_from_env
from groundwork.adapters.model.replay import RecordingModel
from groundwork.core.services.extraction import (
    PROMPT_NAMES,
    ExtractionPrompts,
    Workflow,
    extract_rules,
)
from groundwork.core.services.packs import (
    load_domain_pack,
    load_interviews,
    load_pack_config,
    load_prompt,
)
from groundwork.entrypoints.cli import app
from groundwork.entrypoints.wiring import build_crm
from tests.fakes import StubModel

REPO = Path(__file__).resolve().parents[2]
DOMAINS = REPO / "domains"
runner = CliRunner()


def _scripted(**kwargs: Any) -> dict[str, Any]:
    name = kwargs["schema"].__name__
    if name == "Consolidation":
        return {"duplicates": [], "conflicts": []}
    if name == "Questions":
        return {"questions": ["How should we write to them?"]}
    count = kwargs["user"].split("Rules:\n")[1].count("\n") + 1
    return {
        "rules": [
            {
                "index": n,
                "kind": "practice",
                "statement": f"Practice {n}.",
                "channel": "any",
                "segments": [],
                "personas": [],
                "product_ids": [],
                "claim_text": None,
            }
            for n in range(count)
        ]
    }


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GROUNDWORK_MODEL", "GROUNDWORK_RECORD", "GROUNDWORK_MODEL_EXTRACTION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("GROUNDWORK_MODEL_CHEAP", raising=False)


@pytest.fixture
def traces(tmp_path: Path, env: None) -> Path:
    """Record a stub run of the acme pack, as `GROUNDWORK_RECORD=1` would."""
    pack_dir = REPO / "client_packs" / "acme"
    config = load_pack_config(pack_dir)
    traces = tmp_path / "traces"
    recorder = RecordingModel(
        StubModel(structured=_scripted),
        Recordings(traces / "acme" / "model"),
        specs_from_env({}),
    )
    workflow = Workflow(
        pack="acme",
        domain=load_domain_pack(DOMAINS, config.domain),
        crm=build_crm(pack_dir, config),
        model=recorder,
        prompts=ExtractionPrompts(
            **{k: load_prompt(DOMAINS, config.domain, n) for k, n in PROMPT_NAMES.items()}
        ),
    )
    extract_rules(workflow, load_interviews(pack_dir))
    return traces


def _extract(traces: Path, out: Path) -> Result:
    args = ["extract-rules", "--pack", "acme", "--packs-dir", str(REPO / "client_packs")]
    args += ["--domains-dir", str(DOMAINS), "--traces-dir", str(traces), "--out-dir", str(out)]
    return runner.invoke(app, args)


def test_replay_reproduces_the_run_byte_for_byte(traces: Path, tmp_path: Path) -> None:
    first, second = _extract(traces, tmp_path / "a"), _extract(traces, tmp_path / "b")
    assert first.exit_code == 0, first.output
    assert second.output.splitlines()[2:] == first.output.splitlines()[2:]
    assert "acme:" in first.output and "rule(s) proposed" in first.output
    for name in ("rules.proposed.yaml", "extraction_report.yaml"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    assert "status: proposed" in (tmp_path / "a" / "rules.proposed.yaml").read_text()
    assert not (tmp_path / "a" / "rules.yaml").exists()


def test_replay_never_touches_the_network(
    traces: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("network access during replay")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    result = _extract(traces, tmp_path / "out")
    assert result.exit_code == 0, result.output


def test_a_replay_miss_is_reported_with_the_command_to_record(tmp_path: Path, env: None) -> None:
    result = _extract(tmp_path / "empty-traces", tmp_path / "out")
    assert result.exit_code == 1
    assert "FAILED acme-i-1: ReplayMissError" in result.output
    assert "GROUNDWORK_RECORD=1" in result.output


def test_an_unknown_model_adapter_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROUNDWORK_MODEL", "gpt")
    result = _extract(tmp_path, tmp_path / "out")
    assert result.exit_code == 1
    assert "unknown model adapter 'gpt' (valid: claude, replay)" in result.output


@pytest.mark.parametrize("value", ["x", "0"])
def test_a_bad_concurrency_value_is_explained(
    traces: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("GROUNDWORK_MAX_CONCURRENCY", value)
    result = _extract(traces, tmp_path / "out")
    assert result.exit_code == 1
    assert "GROUNDWORK_MAX_CONCURRENCY must be a positive integer" in result.output


def test_an_invalid_pack_is_reported(tmp_path: Path) -> None:
    packs = tmp_path / "client_packs"
    shutil.copytree(REPO / "client_packs" / "acme", packs / "acme")
    (packs / "acme" / "interviews" / "acme-i-1.md").write_text("no front matter")
    args = ["extract-rules", "--pack", "acme", "--packs-dir", str(packs)]
    result = runner.invoke(app, [*args, "--domains-dir", str(DOMAINS)])
    assert result.exit_code == 1
    assert "missing YAML front matter" in result.output
