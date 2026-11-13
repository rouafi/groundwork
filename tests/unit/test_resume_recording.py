"""Resuming a recording: valid recordings are reused, only the missing ones go live."""

from pathlib import Path
from typing import Any

import pytest

from groundwork.adapters.agent.replay import ResumingAgent
from groundwork.adapters.embedding.replay import EmbeddingRecordings, RecordingEmbedding
from groundwork.adapters.model.recording import DEFAULT_SPECS, Recordings
from groundwork.adapters.model.replay import RecordingModel
from groundwork.core.domain.errors import TraceMissError, TraceStaleError
from groundwork.core.domain.harmonize import AgentResult, ContextPack, HarmonizeRequest
from groundwork.core.domain.policy import Limits
from tests.fakes import HashEmbedding, StubModel


def test_a_resumed_model_call_with_a_recording_does_not_go_live(tmp_path: Path) -> None:
    recordings = Recordings(tmp_path)
    first = StubModel(text=lambda **_: "once")
    RecordingModel(first, recordings, DEFAULT_SPECS).complete_text(
        tier="cheap", system="s", user="u"
    )

    second = StubModel(text=lambda **_: "twice")
    resumed = RecordingModel(second, recordings, DEFAULT_SPECS, reuse=True)
    assert resumed.complete_text(tier="cheap", system="s", user="u").value == "once"
    assert resumed.complete_text(tier="cheap", system="s", user="new").value == "twice"


def test_without_resume_a_recording_is_made_afresh(tmp_path: Path) -> None:
    recordings = Recordings(tmp_path)
    RecordingModel(StubModel(text=lambda **_: "once"), recordings, DEFAULT_SPECS).complete_text(
        tier="cheap", system="s", user="u"
    )
    again = RecordingModel(StubModel(text=lambda **_: "twice"), recordings, DEFAULT_SPECS)
    assert again.complete_text(tier="cheap", system="s", user="u").value == "twice"


def test_a_resumed_embedding_only_embeds_the_missing_texts(tmp_path: Path) -> None:
    recordings = EmbeddingRecordings(tmp_path)
    RecordingEmbedding(HashEmbedding(), recordings, "m").embed(["a", "b"], "document")

    inner = HashEmbedding()
    resumed = RecordingEmbedding(inner, recordings, "m", reuse=True)
    vectors = resumed.embed(["a", "c", "b"], "document")

    assert inner.calls == [(("c",), "document")]
    assert vectors == HashEmbedding().embed(["a", "c", "b"], "document")


class _Agent:
    def __init__(self, outcome: Exception | None) -> None:
        self.outcome = outcome
        self.runs = 0

    def run(self, **_: Any) -> AgentResult:
        self.runs += 1
        if self.outcome:
            raise self.outcome
        return AgentResult.model_construct()


def _run(agent: ResumingAgent) -> AgentResult:
    return agent.run(
        system="s",
        context=ContextPack.model_construct(),
        request=HarmonizeRequest.model_construct(),
        limits=Limits.model_construct(),
    )


@pytest.mark.parametrize("error", [TraceMissError("c", "p"), TraceStaleError("c", "request")])
def test_a_missing_or_stale_trace_is_run_live(error: Exception) -> None:
    replay, live = _Agent(error), _Agent(None)
    _run(ResumingAgent(replay, live))
    assert (replay.runs, live.runs) == (1, 1)


def test_a_valid_trace_is_replayed_and_never_run_live() -> None:
    replay, live = _Agent(None), _Agent(None)
    _run(ResumingAgent(replay, live))
    assert (replay.runs, live.runs) == (1, 0)
