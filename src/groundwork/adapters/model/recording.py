"""What the Claude and replay adapters share: tier specs, request keys, the recordings store.

A recording holds one logical call: its inputs, its final validated answer and its
token usage. Never keys, never headers. The key hashes every input that can change
the answer, so editing a prompt, a schema or a model id invalidates the recording.
"""

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from groundwork.core.domain.errors import ReplayMissError
from groundwork.core.domain.knowhow import Usage
from groundwork.core.ports.model import Tier


@dataclass(frozen=True)
class ModelSpec:
    """The model and effort a tier maps to."""

    model_id: str
    effort: str


DEFAULT_SPECS: Mapping[str, ModelSpec] = MappingProxyType(
    {
        "extraction": ModelSpec(model_id="claude-sonnet-5-5", effort="high"),
        "cheap": ModelSpec(model_id="claude-haiku-5-5", effort="low"),
    }
)
SPEC_ENV = MappingProxyType(
    {"extraction": "GROUNDWORK_MODEL_EXTRACTION", "cheap": "GROUNDWORK_MODEL_CHEAP"}
)


def specs_from_env(env: Mapping[str, str] = os.environ) -> Mapping[str, ModelSpec]:
    """Default specs, with model ids overridable per tier by environment variables."""
    return MappingProxyType(
        {
            tier: ModelSpec(model_id=env.get(SPEC_ENV[tier]) or spec.model_id, effort=spec.effort)
            for tier, spec in DEFAULT_SPECS.items()
        }
    )


def request_payload(
    method: str, tier: Tier, specs: Mapping[str, ModelSpec], **inputs: Any
) -> dict[str, Any]:
    """Every input that can change the answer, in a JSON-serializable form."""
    spec = specs[tier]
    return {"method": method, "model_id": spec.model_id, "effort": spec.effort, **inputs}


def call_key(payload: Mapping[str, Any]) -> str:
    """sha256 of the canonical JSON of the payload (sorted keys, no whitespace)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Recordings:
    """One JSON file per call under a pack's trace directory."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path(self, key: str) -> Path:
        return self._directory / f"{key}.json"

    def read(self, key: str) -> dict[str, Any]:
        path = self.path(key)
        if not path.is_file():
            raise ReplayMissError(key, str(path))
        record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return record

    def save(self, payload: Mapping[str, Any], answer: Any, usage: Usage, model: str | None) -> str:
        """Write one call: inputs, final answer, usage and the model that answered."""
        key = call_key(payload)
        record = {
            "key": key,
            "request": dict(payload),
            "answer": answer,
            "usage": usage.model_dump(),
            "model": model,
        }
        self._directory.mkdir(parents=True, exist_ok=True)
        text = json.dumps(record, sort_keys=True, indent=2, ensure_ascii=False)
        self.path(key).write_text(text + "\n", encoding="utf-8")
        return key
