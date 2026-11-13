"""The committed demo: replayed with no environment, it shows the three routes."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from groundwork.entrypoints.cli import app

REPO = Path(__file__).resolve().parents[2]
TRACES = REPO / "traces"
runner = CliRunner()
EVENTS_OK = ["request", "context_pack", "output", "claim_check", "decision"]


@pytest.fixture(autouse=True)
def _replay_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GROUNDWORK_MODEL", "GROUNDWORK_EMBEDDING", "GROUNDWORK_RECORD"):
        monkeypatch.delenv(name, raising=False)


def _snapshot() -> dict[str, bytes]:
    return {str(p): p.read_bytes() for p in TRACES.rglob("*") if p.is_file()}


def test_the_demo_replays_with_no_environment_and_shows_the_three_routes() -> None:
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0, result.output
    for pack in ("acme", "beta"):
        assert f"{pack}: 3 case(s): 1 approval, 1 auto_send, 1 blocked" in result.output
    assert "Subject: (draft, unchanged)" in result.output


def test_replaying_the_demo_changes_no_recorded_file() -> None:
    before = _snapshot()
    assert runner.invoke(app, ["demo"]).exit_code == 0
    assert _snapshot() == before


@pytest.mark.parametrize("pack", ["acme", "beta"])
def test_every_recorded_trace_ends_in_a_decision_and_holds_no_secret(pack: str) -> None:
    traces = sorted((TRACES / pack).glob("*.jsonl"))
    assert len(traces) >= 3  # the demo traces, plus the ones recorded by the evals
    for path in traces:
        text = path.read_text(encoding="utf-8")
        events = [json.loads(line) for line in text.splitlines()]
        types = [e["type"] for e in events]
        assert types[:2] == ["request", "context_pack"] and types[-1] == "decision"
        assert "output" in types and "error" not in types
        assert all("time" not in key and "date" not in key for e in events for key in e)
        for needle in ("sk-ant", "x-api-key", "api_key", "Bearer "):
            assert needle not in text, (path.name, needle)


def test_an_internal_case_auto_sends_an_external_one_never_does() -> None:
    for pack in ("acme", "beta"):
        for path in (TRACES / pack).glob("*.jsonl"):
            events = [json.loads(line) for line in path.read_text().splitlines()]
            channel = events[0]["request"]["channel"]
            route = events[-1]["route"]
            assert route in {"auto_send", "approval", "blocked"}
            if channel == "external":
                assert route != "auto_send", path.name
