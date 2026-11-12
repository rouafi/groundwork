from pathlib import Path

import pytest

from groundwork.adapters.model.claude import ClaudeModel
from groundwork.adapters.model.replay import RecordingModel, ReplayModel
from groundwork.core.domain.errors import PackError
from groundwork.core.domain.pack import PackConfig
from groundwork.entrypoints.wiring import build_model

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
