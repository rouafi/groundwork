"""`groundwork index` end to end, on a copy of the acme pack and recorded stub calls."""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from groundwork.adapters.embedding.replay import EmbeddingRecordings, RecordingEmbedding
from groundwork.adapters.embedding.voyage import VOYAGE_MODEL
from groundwork.adapters.model.recording import DEFAULT_SPECS, Recordings
from groundwork.adapters.model.replay import RecordingModel
from groundwork.core.services.indexing import build_index
from groundwork.core.services.packs import (
    CHUNKS_FILE,
    load_chunks,
    load_interviews,
    load_prompt,
    load_retrieval_questions,
)
from groundwork.entrypoints.cli import app
from tests.fakes import HashEmbedding, StubModel

REPO = Path(__file__).resolve().parents[2]
DOMAINS = REPO / "domains"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _replay_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GROUNDWORK_MODEL", "GROUNDWORK_EMBEDDING", "GROUNDWORK_RECORD"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def packs(tmp_path: Path) -> Path:
    """A copy of the shipped acme pack, without its committed index."""
    root = tmp_path / "client_packs"
    shutil.copytree(REPO / "client_packs" / "acme", root / "acme")
    shutil.rmtree(root / "acme" / "index", ignore_errors=True)
    return root


@pytest.fixture
def traces(tmp_path: Path, packs: Path) -> Path:
    """Recordings of the stub model and the hash embedding for every chunk of the pack."""
    root = tmp_path / "traces"
    model = RecordingModel(
        StubModel(text=lambda **_: "The expert on how the team writes."),
        Recordings(root / "acme" / "model"),
        DEFAULT_SPECS,
    )
    embedding = RecordingEmbedding(
        HashEmbedding(), EmbeddingRecordings(root / "acme" / "embeddings"), VOYAGE_MODEL
    )
    system = load_prompt(DOMAINS, "comms", "contextualize")
    build_index(load_interviews(packs / "acme"), model, embedding, system)
    embedding.embed([q.question for q in load_retrieval_questions(packs / "acme")], "query")
    return root


def _index(packs: Path, traces: Path, out: Path | None = None) -> Result:
    args = [
        "index",
        "--pack", "acme",
        "--packs-dir", str(packs),
        "--domains-dir", str(DOMAINS),
        "--traces-dir", str(traces),
    ]  # fmt: skip
    return runner.invoke(app, [*args, "--out-dir", str(out)] if out else args)


def test_index_writes_one_chunk_per_recorded_chunk(packs: Path, traces: Path) -> None:
    result = _index(packs, traces)
    assert result.exit_code == 0, result.output
    chunks = load_chunks(packs / "acme")
    assert chunks
    assert all(c.context and c.embedding for c in chunks)
    assert f"{len(chunks)} chunk(s) from 3 interview(s)" in result.output


def test_index_is_idempotent(packs: Path, traces: Path) -> None:
    path = packs / "acme" / CHUNKS_FILE
    _index(packs, traces)
    first = path.read_bytes()
    _index(packs, traces)
    assert path.read_bytes() == first


def test_index_can_write_elsewhere_and_leaves_the_pack_alone(
    packs: Path, traces: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    assert _index(packs, traces, out).exit_code == 0
    assert (out / CHUNKS_FILE).is_file()
    assert not (packs / "acme" / CHUNKS_FILE).exists()


def test_index_without_recordings_names_what_to_record(packs: Path, tmp_path: Path) -> None:
    result = _index(packs, tmp_path / "empty-traces")
    assert result.exit_code == 1
    assert "no recording" in result.output
    assert not (packs / "acme" / CHUNKS_FILE).exists()


def test_index_of_a_pack_without_interviews_is_an_error(packs: Path, traces: Path) -> None:
    shutil.rmtree(packs / "acme" / "interviews")
    result = _index(packs, traces)
    assert result.exit_code == 1
    assert "no interviews to index" in result.output


def test_validate_packs_accepts_a_fresh_index_and_names_a_stale_chunk(
    packs: Path, traces: Path
) -> None:
    _index(packs, traces)
    validate = ["validate-packs", "--packs-dir", str(packs), "--domains-dir", str(DOMAINS)]
    assert runner.invoke(app, validate).exit_code == 0

    path = packs / "acme" / CHUNKS_FILE
    path.write_text(path.read_text().replace("catalog", "KATALOG", 1), encoding="utf-8")
    result = runner.invoke(app, validate)
    assert result.exit_code == 1
    assert "acme-i-1-c-001: text is not in interview acme-i-1" in result.output


def test_index_also_needs_the_retrieval_questions_recorded(packs: Path, traces: Path) -> None:
    for recording in (traces / "acme" / "embeddings").glob("*.json"):
        if '"input_type": "query"' in recording.read_text():
            recording.unlink()
    result = _index(packs, traces)
    assert result.exit_code == 1
    assert "no recording for embedding" in result.output
