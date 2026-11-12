"""Composition root: turn a client pack's config into adapters.

The only place that knows which adapter class backs which config name.
Adding a CRM is one entry in `CRM_ADAPTERS` plus the adapter itself.
"""

import functools
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.adapters.model.claude import ClaudeModel
from groundwork.adapters.model.recording import Recordings, specs_from_env
from groundwork.adapters.model.replay import RecordingModel, ReplayModel
from groundwork.core.domain.errors import GroundworkError, ModelError, PackError
from groundwork.core.domain.pack import PackConfig
from groundwork.core.ports.crm import CrmPort
from groundwork.core.ports.model import ModelPort
from groundwork.core.services.packs import (
    CONFIG_FILE,
    load_domain_pack,
    load_pack_config,
    load_prompt,
    load_rules,
)
from groundwork.entrypoints.mcp_server import ServerContext

FIXTURES_SUBDIR = Path("fixtures") / "hubspot"
MODEL_TRACES_SUBDIR = "model"
MODEL_ENV = "GROUNDWORK_MODEL"
RECORD_ENV = "GROUNDWORK_RECORD"
CLAIMS_PROMPT = "extract_claims"

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


def build_server_context(
    pack_dir: Path,
    domains_dir: Path,
    traces_dir: Path,
    env: Mapping[str, str] = os.environ,
) -> ServerContext:
    """Everything the MCP server of one pack reads. Raises `PackError` on a bad pack.

    The model is built on the first claim check only, so the three fact tools work
    with no API key, and a missing key is reported by that tool, not at start.
    """
    config = load_pack_config(pack_dir)
    domain = load_domain_pack(domains_dir, config.domain)
    claims_prompt = load_prompt(domains_dir, config.domain, CLAIMS_PROMPT)

    @functools.cache
    def model() -> ModelPort:
        try:
            return build_model(pack_dir, config, traces_dir, env)
        except GroundworkError:
            raise
        except Exception as exc:  # the SDK client refuses to start, e.g. no API key
            raise ModelError(f"check_claims cannot build its model: {exc}") from exc

    return ServerContext(
        pack=pack_dir.name,
        domain=domain,
        crm=build_crm(pack_dir, config),
        rules=load_rules(pack_dir),
        claims_prompt=claims_prompt,
        model=model,
    )
