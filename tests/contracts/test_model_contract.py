"""ModelPort contract: one suite, every adapter that can run without the network.

Written against the port only. To cover a new adapter, add a factory to `ADAPTERS`.
"""

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel

from groundwork.core.ports.model import ModelPort
from tests.fakes import StubModel

DOCUMENT = "We keep emails short. We never put a discount in writing! Prices come from the catalog."


class Verdict(BaseModel):
    label: str


def _stub() -> ModelPort:
    return StubModel(structured=lambda **_: {"label": "ok"}, text=lambda **_: "a short answer")


ADAPTERS: dict[str, Callable[[], ModelPort]] = {"stub": _stub}


@pytest.fixture(params=sorted(ADAPTERS))
def model(request: pytest.FixtureRequest) -> ModelPort:
    return ADAPTERS[request.param]()


def _structured(model: ModelPort) -> Any:
    return model.complete_structured(
        tier="cheap", system="Classify.", user="Label this.", schema=Verdict, document=DOCUMENT
    )


def test_structured_answer_is_an_instance_of_the_schema(model: ModelPort) -> None:
    assert isinstance(_structured(model).value, Verdict)


def test_text_answer_is_a_string(model: ModelPort) -> None:
    answer = model.complete_text(tier="cheap", system="Answer.", user="Say something.")
    assert isinstance(answer.value, str)


def test_cited_quotes_are_verbatim_spans_of_the_document(model: ModelPort) -> None:
    answer = model.cite(
        tier="extraction", system="Extract.", instruction="List practices.", document=DOCUMENT
    )
    quotes = [q for statement in answer.value for q in statement.quotes]
    assert quotes
    assert all(DOCUMENT[q.start : q.end] == q.text for q in quotes)


def test_every_answer_reports_its_cost(model: ModelPort) -> None:
    assert _structured(model).usage.input_tokens > 0


def test_same_inputs_give_the_same_answer(model: ModelPort) -> None:
    assert _structured(model) == _structured(model)
