"""Record and replay model calls.

`RecordingModel` wraps any ModelPort and writes each call it serves.
`ReplayModel` serves those recordings. It never calls the network and never falls
back to a live call. Both build the key the same way, so what one writes the other reads.
"""

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel

from groundwork.adapters.model.recording import (
    ModelSpec,
    Recordings,
    call_key,
    request_payload,
)
from groundwork.core.domain.errors import ReplayMissError
from groundwork.core.domain.knowhow import Usage
from groundwork.core.ports.model import Answer, CitedStatement, ModelPort, Tier


def _structured_inputs(
    system: str, user: str, schema: type[BaseModel], document: str | None
) -> dict[str, Any]:
    return {
        "system": system,
        "user": user,
        "document": document,
        "schema_name": schema.__name__,
        "schema_json": schema.model_json_schema(),
    }


def _text_inputs(system: str, user: str, document: str | None) -> dict[str, Any]:
    return {"system": system, "user": user, "document": document}


def _cite_inputs(system: str, instruction: str, document: str) -> dict[str, Any]:
    return {"system": system, "instruction": instruction, "document": document}


class ReplayModel:
    """A ModelPort backed by recordings. A missing recording raises `ReplayMissError`."""

    def __init__(self, recordings: Recordings, specs: Mapping[str, ModelSpec]) -> None:
        self._recordings = recordings
        self._specs = specs

    def complete_structured[S: BaseModel](
        self, *, tier: Tier, system: str, user: str, schema: type[S], document: str | None = None
    ) -> Answer[S]:
        inputs = _structured_inputs(system, user, schema, document)
        record = self._read("complete_structured", tier, inputs)
        return _answer(record, schema.model_validate(record["answer"]))

    def complete_text(
        self, *, tier: Tier, system: str, user: str, document: str | None = None
    ) -> Answer[str]:
        record = self._read("complete_text", tier, _text_inputs(system, user, document))
        return _answer(record, str(record["answer"]))

    def cite(
        self, *, tier: Tier, system: str, instruction: str, document: str
    ) -> Answer[tuple[CitedStatement, ...]]:
        record = self._read("cite", tier, _cite_inputs(system, instruction, document))
        statements = tuple(CitedStatement.model_validate(s) for s in record["answer"])
        return _answer(record, statements)

    def _read(self, method: str, tier: Tier, inputs: dict[str, Any]) -> dict[str, Any]:
        return self._recordings.read(call_key(request_payload(method, tier, self._specs, **inputs)))


class RecordingModel:
    """A ModelPort that delegates to `inner` and records every call it serves.

    With `reuse`, a call that already has a recording is served from it and only the
    missing ones go live: a resumed recording does not pay twice for the same call.
    """

    def __init__(
        self,
        inner: ModelPort,
        recordings: Recordings,
        specs: Mapping[str, ModelSpec],
        reuse: bool = False,
    ) -> None:
        self._inner = inner
        self._recordings = recordings
        self._specs = specs
        self._replay = ReplayModel(recordings, specs) if reuse else None

    def _reused[T](self, serve: Callable[[ModelPort], Answer[T]]) -> Answer[T] | None:
        if self._replay is None:
            return None
        try:
            return serve(self._replay)
        except ReplayMissError:
            return None

    def complete_structured[S: BaseModel](
        self, *, tier: Tier, system: str, user: str, schema: type[S], document: str | None = None
    ) -> Answer[S]:
        reused = self._reused(
            lambda m: m.complete_structured(
                tier=tier, system=system, user=user, schema=schema, document=document
            )
        )
        if reused is not None:
            return reused
        answer = self._inner.complete_structured(
            tier=tier, system=system, user=user, schema=schema, document=document
        )
        inputs = _structured_inputs(system, user, schema, document)
        self._save(
            "complete_structured", tier, inputs, answer, answer.value.model_dump(mode="json")
        )
        return answer

    def complete_text(
        self, *, tier: Tier, system: str, user: str, document: str | None = None
    ) -> Answer[str]:
        reused = self._reused(
            lambda m: m.complete_text(tier=tier, system=system, user=user, document=document)
        )
        if reused is not None:
            return reused
        answer = self._inner.complete_text(tier=tier, system=system, user=user, document=document)
        self._save(
            "complete_text", tier, _text_inputs(system, user, document), answer, answer.value
        )
        return answer

    def cite(
        self, *, tier: Tier, system: str, instruction: str, document: str
    ) -> Answer[tuple[CitedStatement, ...]]:
        reused = self._reused(
            lambda m: m.cite(tier=tier, system=system, instruction=instruction, document=document)
        )
        if reused is not None:
            return reused
        answer = self._inner.cite(
            tier=tier, system=system, instruction=instruction, document=document
        )
        statements = [s.model_dump(mode="json") for s in answer.value]
        self._save("cite", tier, _cite_inputs(system, instruction, document), answer, statements)
        return answer

    def _save(
        self, method: str, tier: Tier, inputs: dict[str, Any], answer: Answer[Any], value: Any
    ) -> None:
        payload = request_payload(method, tier, self._specs, **inputs)
        self._recordings.save(payload, value, answer.usage, answer.model)


def _answer[T](record: Mapping[str, Any], value: T) -> Answer[T]:
    return Answer(
        value=value, usage=Usage.model_validate(record["usage"]), model=record.get("model")
    )
