from pathlib import Path

import pytest

from groundwork.adapters.embedding.replay import RecordingEmbedding, ReplayEmbedding
from groundwork.adapters.embedding.voyage import VoyageEmbedding
from groundwork.adapters.model.claude import ClaudeModel
from groundwork.adapters.model.replay import RecordingModel, ReplayModel
from groundwork.adapters.vector.lance import LanceDbStore
from groundwork.adapters.vector.memory import InMemoryVectorStore
from groundwork.core.domain.errors import ModelError, PackError
from groundwork.core.domain.pack import PackConfig
from groundwork.entrypoints.wiring import build_embedding, build_model, build_store

CONFIG = PackConfig(
    crm="fixture", messaging="console", vector_store="lancedb", model="replay", domain="comms"
)
PACK = Path("client_packs/acme")


def test_the_pack_config_selects_the_model_by_default(tmp_path: Path) -> None:
    assert isinstance(build_model(PACK, CONFIG, tmp_path, env={}), ReplayModel)


def test_the_environment_overrides_the_pack_config(tmp_path: Path) -> None:
    env = {"GROUNDWORK_MODEL": "claude", "ANTHROPIC_API_KEY": "test-key-not-real"}
    assert isinstance(build_model(PACK, CONFIG, tmp_path, env=env), ClaudeModel)


def test_recording_wraps_the_live_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    env = {"GROUNDWORK_MODEL": "claude", "GROUNDWORK_RECORD": "1"}
    assert isinstance(build_model(PACK, CONFIG, tmp_path, env=env), RecordingModel)


def test_an_unknown_model_is_a_pack_error(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="unknown model adapter 'gpt'"):
        build_model(PACK, CONFIG.model_copy(update={"model": "gpt"}), tmp_path, env={})


def test_a_live_model_without_credentials_names_the_missing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(ModelError, match=r"ANTHROPIC_API_KEY.*\.env"):
        build_model(PACK, CONFIG, tmp_path, env={"GROUNDWORK_MODEL": "claude"})


def test_the_pack_config_embeds_with_replay_by_default() -> None:
    assert CONFIG.embedding == "replay"
    assert isinstance(build_embedding(PACK, CONFIG, Path("traces"), env={}), ReplayEmbedding)


def test_voyage_needs_its_key_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    with pytest.raises(ModelError, match="VOYAGE_API_KEY"):
        build_embedding(PACK, CONFIG, tmp_path, env={"GROUNDWORK_EMBEDDING": "voyage"})


def test_voyage_with_a_key_is_live_and_recording_wraps_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key-not-real")
    live = {"GROUNDWORK_EMBEDDING": "voyage"}
    assert isinstance(build_embedding(PACK, CONFIG, tmp_path, env=live), VoyageEmbedding)
    recording = {**live, "GROUNDWORK_RECORD": "1"}
    assert isinstance(build_embedding(PACK, CONFIG, tmp_path, env=recording), RecordingEmbedding)


def test_an_unknown_embedding_is_a_pack_error(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="unknown embedding adapter 'glove'"):
        build_embedding(PACK, CONFIG.model_copy(update={"embedding": "glove"}), tmp_path, env={})


@pytest.mark.parametrize(
    ("name", "kind"), [("lancedb", LanceDbStore), ("memory", InMemoryVectorStore)]
)
def test_the_pack_config_selects_the_vector_store(name: str, kind: type) -> None:
    assert isinstance(build_store(PACK, CONFIG.model_copy(update={"vector_store": name})), kind)


def test_an_unknown_vector_store_lists_the_valid_ones() -> None:
    with pytest.raises(PackError, match=r"unknown vector_store 'faiss' \(valid: lancedb, memory\)"):
        build_store(PACK, CONFIG.model_copy(update={"vector_store": "faiss"}))


def test_resume_makes_the_recording_model_reuse_what_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    resumed = build_model(
        PACK, CONFIG, tmp_path, env={"GROUNDWORK_MODEL": "claude", "GROUNDWORK_RECORD": "resume"}
    )
    fresh = build_model(
        PACK, CONFIG, tmp_path, env={"GROUNDWORK_MODEL": "claude", "GROUNDWORK_RECORD": "1"}
    )
    assert isinstance(resumed, RecordingModel) and resumed._replay is not None
    assert isinstance(fresh, RecordingModel) and fresh._replay is None
