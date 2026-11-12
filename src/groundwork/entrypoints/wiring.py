"""Composition root: turn a client pack's config into adapters.

The only place that knows which adapter class backs which config name.
Adding a CRM is one entry in `CRM_ADAPTERS` plus the adapter itself.
"""

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.adapters.model.claude import ClaudeModel
from groundwork.adapters.model.recording import Recordings, specs_from_env
from groundwork.adapters.model.replay import RecordingModel, ReplayModel
from groundwork.core.domain.errors import PackError
from groundwork.core.domain.pack import PackConfig
from groundwork.core.ports.crm import CrmPort
from groundwork.core.ports.model import ModelPort
from groundwork.core.services.packs import CONFIG_FILE

FIXTURES_SUBDIR = Path("fixtures") / "hubspot"
MODEL_TRACES_SUBDIR = "model"
MODEL_ENV = "GROUNDWORK_MODEL"
RECORD_ENV = "GROUNDWORK_RECORD"

CRM_ADAPTERS: Mapping[str, Callable[[Path], CrmPort]] = MappingProxyType(
    {"fixture": lambda pack_dir: FixtureCrm(pack_dir / FIXTURES_SUBDIR)}
)
MODEL_ADAPTERS = ("claude", "replay")


def build_crm(pack_dir: Path, config: PackConfig) -> CrmPort:
    """Build the CRM adapter the pack selects with `crm:` in its config."""
    factory = CRM_ADAPTERS.get(config.crm)
    if factory is None:
        valid = ", ".join(sorted(CRM_ADAPTERS))
        raise PackError(
            f"{pack_dir / CONFIG_FILE}: unknown crm adapter {config.crm!r} (valid: {valid})"
        )
    return factory(pack_dir)


def build_model(
    pack_dir: Path,
    config: PackConfig,
    traces_dir: Path,
    env: Mapping[str, str] = os.environ,
) -> ModelPort:
    """Build the model adapter: `GROUNDWORK_MODEL` overrides `model:` in the pack config.

    Recordings live in `<traces_dir>/<pack>/model/`. With `claude` and
    `GROUNDWORK_RECORD=1`, every call is recorded there for replay.
    """
    name = env.get(MODEL_ENV) or config.model
    specs = specs_from_env(env)
    recordings = Recordings(traces_dir / pack_dir.name / MODEL_TRACES_SUBDIR)
    if name == "replay":
        return ReplayModel(recordings, specs)
    if name == "claude":
        import anthropic  # imported here so replay runs never load the SDK client

        model: ModelPort = ClaudeModel(anthropic.Anthropic(), specs)
        return RecordingModel(model, recordings, specs) if env.get(RECORD_ENV) == "1" else model
    valid = ", ".join(MODEL_ADAPTERS)
    raise PackError(f"{pack_dir / CONFIG_FILE}: unknown model adapter {name!r} (valid: {valid})")
