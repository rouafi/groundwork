"""ModelPort contract: one suite, every adapter that can run without the network.

Written against the port only. To cover a new adapter, add a factory to `ADAPTERS`.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel

from groundwork.adapters.model.recording import DEFAULT_SPECS, Recordings
from groundwork.adapters.model.replay import RecordingModel, ReplayModel
from groundwork.core.ports.model import Answer, CitedStatement, ModelPort
from tests.fakes import StubModel

DOCUMENT = "We keep emails short. We never put a discount in writing! Prices come from the catalog."


class Verdict(BaseModel):
    label: str


def _structured(model: ModelPort) -> Answer[Verdict]:
    return model.complete_structured(
        tier="cheap", system="Classify.", user="Label this.", schema=Verdict, document=DOCUMENT
    )


def _text(model: ModelPort) -> Answer[str]:
    return model.complete_text(tier="cheap", system="Answer.", user="Say something.")


def _cite(model: ModelPort) -> Answer[tuple[CitedStatement, ...]]:
    return model.cite(
        tier="extraction", system="Extract.", instruction="List practices.", document=DOCUMENT
    )


def _stub() -> ModelPort:
    return StubModel(structured=lambda **_: {"label": "ok"}, text=lambda **_: "a short answer")


def _replay(directory: Path) -> ModelPort:
    """Record the stub's answers to every call of this suite, then serve them on replay."""
    recordings = Recordings(directory)
    recorder = RecordingModel(_stub(), recordings, DEFAULT_SPECS)
    for call in (_structured, _text, _cite):
        call(recorder)
    return ReplayModel(recordings, DEFAULT_SPECS)


ADAPTERS: dict[str, Callable[[Path], ModelPort]] = {
    "stub": lambda _: _stub(),
    "replay": _replay,
}


@pytest.fixture(params=sorted(ADAPTERS))
def model(request: pytest.FixtureRequest, tmp_path: Path) -> ModelPort:
    return ADAPTERS[request.param](tmp_path)


def test_structured_answer_is_an_instance_of_the_schema(model: ModelPort) -> None:
    assert isinstance(_structured(model).value, Verdict)


def test_text_answer_is_a_string(model: ModelPort) -> None:
    assert isinstance(_text(model).value, str)


def test_cited_quotes_are_verbatim_spans_of_the_document(model: ModelPort) -> None:
    quotes = [q for statement in _cite(model).value for q in statement.quotes]
    assert quotes
    assert all(DOCUMENT[q.start : q.end] == q.text for q in quotes)


def test_every_answer_reports_its_cost(model: ModelPort) -> None:
    assert _structured(model).usage.input_tokens > 0


def test_same_inputs_give_the_same_answer(model: ModelPort) -> None:
    assert _structured(model) == _structured(model)
