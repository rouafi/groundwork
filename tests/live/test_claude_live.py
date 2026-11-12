"""Real calls to the Claude API. Manual only: `uv run pytest -m live`. Never run in CI."""

import os

import anthropic
import pytest
from pydantic import BaseModel

from groundwork.adapters.model.claude import ClaudeModel
from groundwork.adapters.model.recording import specs_from_env

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY"
)

DOC = "We keep emails to clients short. We never put a discount in writing."


class Label(BaseModel):
    label: str


def test_cite_and_structured_output_against_the_api() -> None:
    model = ClaudeModel(anthropic.Anthropic(), specs_from_env())
    cited = model.cite(
        tier="extraction", system="Extract practices.", instruction="List them.", document=DOC
    )
    quotes = [q for s in cited.value for q in s.quotes]
    assert quotes and all(DOC[q.start : q.end] == q.text for q in quotes)
    label = model.complete_structured(
        tier="cheap", system="Classify.", user="Is this about tone?", schema=Label, document=DOC
    )
    assert isinstance(label.value, Label)
