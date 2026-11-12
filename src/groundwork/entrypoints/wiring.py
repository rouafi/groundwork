"""Composition root: turn a client pack's config into adapters.

The only place that knows which adapter class backs which config name.
Adding a CRM is one entry in `CRM_ADAPTERS` plus the adapter itself.
"""

import functools
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from groundwork.adapters.agent.claude import ClaudeAgent
from groundwork.adapters.agent.replay import ReplayAgent
from groundwork.adapters.agent.toolbox import McpToolBox
from groundwork.adapters.approval.file import FileApproval
from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.adapters.embedding.replay import (
    EmbeddingRecordings,
    RecordingEmbedding,
    ReplayEmbedding,
)
from groundwork.adapters.embedding.voyage import VOYAGE_MODEL, VoyageEmbedding
from groundwork.adapters.messaging.console import ConsoleMessaging
from groundwork.adapters.model.claude import ClaudeModel
from groundwork.adapters.model.recording import Recordings, specs_from_env
from groundwork.adapters.model.replay import RecordingModel, ReplayModel
from groundwork.adapters.vector.lance import LanceDbStore
from groundwork.adapters.vector.memory import InMemoryVectorStore
from groundwork.core.domain.errors import ModelError, PackError
from groundwork.core.domain.pack import PackConfig
from groundwork.core.domain.search import SearchHit
from groundwork.core.ports.agent import AgentPort
from groundwork.core.ports.crm import CrmPort
from groundwork.core.ports.embedding import EmbeddingPort
from groundwork.core.ports.messaging import MessagingPort
from groundwork.core.ports.model import ModelPort
from groundwork.core.ports.vector_store import VectorStorePort
from groundwork.core.services.harmonize import HarmonizeFlow
from groundwork.core.services.packs import (
    CONFIG_FILE,
    load_chunks,
    load_domain_pack,
    load_domain_policies,
    load_pack_config,
    load_pack_policies,
    load_prompt,
    load_rules,
)
from groundwork.core.services.policy import merge_policies
from groundwork.core.services.retrieval import search_knowhow
from groundwork.entrypoints.mcp_server import ALLOWED_TOOLS, ServerContext, create_server

FIXTURES_SUBDIR = Path("fixtures") / "hubspot"
MODEL_TRACES_SUBDIR = "model"
MODEL_ENV = "GROUNDWORK_MODEL"
RECORD_ENV = "GROUNDWORK_RECORD"
CREDENTIAL_ENVS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
CLAIMS_PROMPT = "extract_claims"
CONTEXT_PROMPT = "contextualize"
HARMONIZE_PROMPT = "harmonize"
PASSAGES = 5
EMBEDDING_ENV = "GROUNDWORK_EMBEDDING"
EMBEDDING_TRACES_SUBDIR = "embeddings"
VOYAGE_KEY_ENV = "VOYAGE_API_KEY"
VOYAGE_RETRIES = 4  # rate limits (3 requests a minute without a payment method) are retried

CRM_ADAPTERS: Mapping[str, Callable[[Path], CrmPort]] = MappingProxyType(
    {"fixture": lambda pack_dir: FixtureCrm(pack_dir / FIXTURES_SUBDIR)}
)
MODEL_ADAPTERS = ("claude", "replay")
MESSAGING_ADAPTERS: Mapping[str, Callable[[str, Path], MessagingPort]] = MappingProxyType(
    {"console": lambda pack, var_dir: ConsoleMessaging(pack, var_dir)}
)
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

        embedding: EmbeddingPort = VoyageEmbedding(Client(max_retries=VOYAGE_RETRIES), VOYAGE_MODEL)
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

    The model and the query embedding are built on first use only, so the fact tools
    work with no API key; a missing key is a `ModelError` the tool reports. The pack's
    index, if it has one, is loaded into the vector store here.
    """
    config = load_pack_config(pack_dir)
    domain = load_domain_pack(domains_dir, config.domain)
    claims_prompt = load_prompt(domains_dir, config.domain, CLAIMS_PROMPT)

    @functools.cache
    def model() -> ModelPort:
        return build_model(pack_dir, config, traces_dir, env)

    @functools.cache
    def embedding() -> EmbeddingPort:
        return build_embedding(pack_dir, config, traces_dir, env)

    chunks = load_chunks(pack_dir)
    store = build_store(pack_dir, config)
    if chunks:
        store.upsert(chunks)

    return ServerContext(
        pack=pack_dir.name,
        domain=domain,
        crm=build_crm(pack_dir, config),
        rules=load_rules(pack_dir),
        claims_prompt=claims_prompt,
        model=model,
        store=store,
        embedding=embedding,
        indexed_chunks=len(chunks),
    )


def build_messaging(pack_dir: Path, config: PackConfig, var_dir: Path) -> MessagingPort:
    """Build the messaging adapter the pack selects with `messaging:` in its config."""
    factory = MESSAGING_ADAPTERS.get(config.messaging)
    if factory is None:
        valid = ", ".join(sorted(MESSAGING_ADAPTERS))
        raise PackError(
            f"{pack_dir / CONFIG_FILE}: unknown messaging adapter {config.messaging!r} "
            f"(valid: {valid})"
        )
    return factory(pack_dir.name, var_dir)


def build_agent(
    pack_dir: Path,
    config: PackConfig,
    traces_dir: Path,
    context: ServerContext,
    env: Mapping[str, str] = os.environ,
) -> AgentPort:
    """Build the agent: `GROUNDWORK_MODEL` overrides `model:` in the pack config.

    `replay` serves the traces in `<traces_dir>/<pack>/`; `claude` runs the tool-use loop
    on the Messages API with the pack's own MCP server as its only tools (ADR 0005).
    """
    name = env.get(MODEL_ENV) or config.model
    if name == "replay":
        return ReplayAgent(traces_dir / pack_dir.name)
    if name == "claude":
        if not any(env.get(k) or os.environ.get(k) for k in CREDENTIAL_ENVS):
            raise ModelError(
                f"{MODEL_ENV}=claude needs ANTHROPIC_API_KEY: set it in .env "
                "and run with uv run --env-file .env"
            )
        import anthropic  # imported here so replay runs never load the SDK client

        return ClaudeAgent(
            anthropic.AsyncAnthropic(),
            lambda: McpToolBox(create_server(context)),
            specs_from_env(env),
            ALLOWED_TOOLS,
        )
    valid = ", ".join(MODEL_ADAPTERS)
    raise PackError(f"{pack_dir / CONFIG_FILE}: unknown model adapter {name!r} (valid: {valid})")


def build_flow(
    pack_dir: Path,
    domains_dir: Path,
    traces_dir: Path,
    var_dir: Path,
    env: Mapping[str, str] = os.environ,
) -> HarmonizeFlow:
    """Everything the harmonization flow of one pack needs. Raises `GroundworkError`.

    Shares the MCP server's context (CRM, rules, index, model) so the agent, the claim
    check and the search all read the same data. Sent emails and approvals go under
    `<var_dir>`; traces under `<traces_dir>/<pack>/`.
    """
    server = build_server_context(pack_dir, domains_dir, traces_dir, env)
    config = load_pack_config(pack_dir)
    policies = merge_policies(
        load_domain_policies(domains_dir, config.domain), load_pack_policies(pack_dir)
    )
    search = None
    if server.indexed_chunks:

        def search(query: str) -> tuple[SearchHit, ...]:
            return search_knowhow(query, server.store, server.embedding(), PASSAGES)

    agent = build_agent(pack_dir, config, traces_dir, server, env)
    return HarmonizeFlow(
        crm=server.crm,
        rules=server.rules,
        agent=agent,
        model=server.model(),
        messaging=build_messaging(pack_dir, config, var_dir),
        approval=FileApproval(pack_dir.name, var_dir),
        policies=policies,
        system=load_prompt(domains_dir, config.domain, HARMONIZE_PROMPT),
        claims_prompt=server.claims_prompt,
        traces_dir=traces_dir / pack_dir.name,
        search=search,
        internal_recipient=config.internal_recipient,
        write_traces=not isinstance(agent, ReplayAgent),
        replace_traces=env.get(RECORD_ENV) == "1",
    )
