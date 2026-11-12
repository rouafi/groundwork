from pathlib import Path

import pytest
from pydantic import BaseModel

from groundwork.adapters.model.recording import (
    DEFAULT_SPECS,
    ModelSpec,
    Recordings,
    call_key,
    request_payload,
    specs_from_env,
)
from groundwork.adapters.model.replay import RecordingModel, ReplayModel
from groundwork.core.domain.errors import ReplayMissError
from tests.fakes import StubModel


class Label(BaseModel):
    label: str


def test_key_ignores_dict_order_but_not_values() -> None:
    assert call_key({"a": 1, "b": 2}) == call_key({"b": 2, "a": 1})
    assert call_key({"a": 1}) != call_key({"a": 2})


def test_changing_the_model_changes_the_key() -> None:
    other = {**DEFAULT_SPECS, "cheap": ModelSpec(model_id="claude-other", effort="low")}
    first = request_payload("complete_text", "cheap", DEFAULT_SPECS, system="s", user="u")
    second = request_payload("complete_text", "cheap", other, system="s", user="u")
    assert call_key(first) != call_key(second)


def test_specs_can_be_overridden_per_tier_by_env() -> None:
    specs = specs_from_env({"GROUNDWORK_MODEL_CHEAP": "claude-x"})
    assert specs["cheap"].model_id == "claude-x"
    assert specs["extraction"] == DEFAULT_SPECS["extraction"]


def test_miss_names_the_key_and_the_expected_file(tmp_path: Path) -> None:
    replay = ReplayModel(Recordings(tmp_path), DEFAULT_SPECS)
    with pytest.raises(ReplayMissError, match=str(tmp_path)) as exc:
        replay.complete_text(tier="cheap", system="s", user="u")
    assert len(exc.value.key) == 64


def test_what_is_recorded_is_replayed(tmp_path: Path) -> None:
    recordings = Recordings(tmp_path)
    stub = StubModel(structured=lambda **_: {"label": "ok"}, text=lambda **_: "hi")
    recorder = RecordingModel(stub, recordings, DEFAULT_SPECS)
    replay = ReplayModel(recordings, DEFAULT_SPECS)
    doc = "One. Two."

    recorded = recorder.complete_structured(
        tier="cheap", system="s", user="u", schema=Label, document=doc
    )
    replayed = replay.complete_structured(
        tier="cheap", system="s", user="u", schema=Label, document=doc
    )
    assert replayed == recorded

    recorded_text = recorder.complete_text(tier="cheap", system="s", user="u", document=doc)
    assert replay.complete_text(tier="cheap", system="s", user="u", document=doc) == recorded_text

    recorded_cite = recorder.cite(tier="extraction", system="s", instruction="i", document=doc)
    assert (
        replay.cite(tier="extraction", system="s", instruction="i", document=doc) == recorded_cite
    )


def test_recording_holds_inputs_answer_and_usage_only(tmp_path: Path) -> None:
    recordings = Recordings(tmp_path)
    RecordingModel(StubModel(text=lambda **_: "hi"), recordings, DEFAULT_SPECS).complete_text(
        tier="cheap", system="s", user="u"
    )
    (path,) = tmp_path.glob("*.json")
    text = path.read_text()
    assert text.endswith("\n")
    # The key is the file name only: a hash stored under "key" reads as a leaked API key
    # to secret scanners (gitleaks generic-api-key).
    assert set(recordings.read(path.stem)) == {"request", "answer", "usage", "model"}
    assert "api_key" not in text.lower()


def test_editing_the_prompt_is_a_miss(tmp_path: Path) -> None:
    recordings = Recordings(tmp_path)
    RecordingModel(StubModel(), recordings, DEFAULT_SPECS).complete_text(
        tier="cheap", system="s", user="u"
    )
    with pytest.raises(ReplayMissError):
        ReplayModel(recordings, DEFAULT_SPECS).complete_text(tier="cheap", system="s2", user="u")
