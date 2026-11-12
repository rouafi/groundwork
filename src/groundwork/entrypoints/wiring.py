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
from groundwork.adapters.embedding.replay import (
    EmbeddingRecordings,
    RecordingEmbedding,
    ReplayEmbedding,
)
from groundwork.adapters.embedding.voyage import VOYAGE_MODEL, VoyageEmbedding
from groundwork.adapters.model.claude import ClaudeModel
from groundwork.adapters.model.recording import Recordings, specs_from_env
from groundwork.adapters.model.replay import RecordingModel, ReplayModel
from groundwork.adapters.vector.lance import LanceDbStore
from groundwork.adapters.vector.memory import InMemoryVectorStore
from groundwork.core.domain.errors import ModelError, PackError
from groundwork.core.domain.pack import PackConfig
from groundwork.core.ports.crm import CrmPort
from groundwork.core.ports.embedding import EmbeddingPort
from groundwork.core.ports.model import ModelPort
from groundwork.core.ports.vector_store import VectorStorePort
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
CREDENTIAL_ENVS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
CLAIMS_PROMPT = "extract_claims"
CONTEXT_PROMPT = "contextualize"
EMBEDDING_ENV = "GROUNDWORK_EMBEDDING"
EMBEDDING_TRACES_SUBDIR = "embeddings"
VOYAGE_KEY_ENV = "VOYAGE_API_KEY"

CRM_ADAPTERS: Mapping[str, Callable[[Path], CrmPort]] = MappingProxyType(
    {"fixture": lambda pack_dir: FixtureCrm(pack_dir / FIXTURES_SUBDIR)}
)
MODEL_ADAPTERS = ("claude", "replay")
EMBEDDING_ADAPTERS = ("replay", "voyage")
STORE_ADAPTERS: Mapping[str, Callable[[], VectorStorePort]] = MappingProxyType(
    {"lancedb": LanceDbStore, "memory": InMemoryVectorStore}
)


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
        if not any(env.get(k) or os.environ.get(k) for k in CREDENTIAL_ENVS):
            raise ModelError(
                f"{MODEL_ENV}=claude needs ANTHROPIC_API_KEY: set it in .env "
                "and run with uv run --env-file .env"
            )
        import anthropic  # imported here so replay runs never load the SDK client

        model: ModelPort = ClaudeModel(anthropic.Anthropic(), specs)
        return RecordingModel(model, recordings, specs) if env.get(RECORD_ENV) == "1" else model
    valid = ", ".join(MODEL_ADAPTERS)
    raise PackError(f"{pack_dir / CONFIG_FILE}: unknown model adapter {name!r} (valid: {valid})")


def build_embedding(
    pack_dir: Path,
    config: PackConfig,
    traces_dir: Path,
    env: Mapping[str, str] = os.environ,
) -> EmbeddingPort:
    """Build the embedding adapter: `GROUNDWORK_EMBEDDING` overrides `embedding:` in the config.

    Recordings live in `<traces_dir>/<pack>/embeddings/`. With `voyage` and
    `GROUNDWORK_RECORD=1`, every vector is recorded there for replay.
    """
    name = env.get(EMBEDDING_ENV) or config.embedding
    recordings = EmbeddingRecordings(traces_dir / pack_dir.name / EMBEDDING_TRACES_SUBDIR)
    if name == "replay":
        return ReplayEmbedding(recordings, VOYAGE_MODEL)
    if name == "voyage":
        if not (env.get(VOYAGE_KEY_ENV) or os.environ.get(VOYAGE_KEY_ENV)):
            raise ModelError(
                f"{EMBEDDING_ENV}=voyage needs {VOYAGE_KEY_ENV}: set it in .env "
                "and run with uv run --env-file .env"
            )
        from voyageai.client import Client  # imported here so replay runs never load the SDK

        embedding: EmbeddingPort = VoyageEmbedding(Client(), VOYAGE_MODEL)
        if env.get(RECORD_ENV) == "1":
            return RecordingEmbedding(embedding, recordings, VOYAGE_MODEL)
        return embedding
    valid = ", ".join(EMBEDDING_ADAPTERS)
    raise PackError(
        f"{pack_dir / CONFIG_FILE}: unknown embedding adapter {name!r} (valid: {valid})"
    )


def build_store(pack_dir: Path, config: PackConfig) -> VectorStorePort:
    """Build the vector store the pack selects with `vector_store:` in its config."""
    factory = STORE_ADAPTERS.get(config.vector_store)
    if factory is None:
        valid = ", ".join(sorted(STORE_ADAPTERS))
        raise PackError(
            f"{pack_dir / CONFIG_FILE}: unknown vector_store {config.vector_store!r} "
            f"(valid: {valid})"
        )
    return factory()


def build_server_context(
    pack_dir: Path,
    domains_dir: Path,
    traces_dir: Path,
    env: Mapping[str, str] = os.environ,
) -> ServerContext:
    """Everything the MCP server of one pack reads. Raises `PackError` on a bad pack.

    The model is built on the first claim check only, so the three fact tools work
    with no API key; a missing key is a `ModelError` that `check_claims` reports.
    """
    config = load_pack_config(pack_dir)
    domain = load_domain_pack(domains_dir, config.domain)
    claims_prompt = load_prompt(domains_dir, config.domain, CLAIMS_PROMPT)

    @functools.cache
    def model() -> ModelPort:
        return build_model(pack_dir, config, traces_dir, env)

    return ServerContext(
        pack=pack_dir.name,
        domain=domain,
        crm=build_crm(pack_dir, config),
        rules=load_rules(pack_dir),
        claims_prompt=claims_prompt,
        model=model,
    )
