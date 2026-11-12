# Architecture

## Layers
| Layer | Path | Contains | Depends on |
|---|---|---|---|
| Domain | `src/groundwork/core/domain` | Contact, Deal, Product, Rule, EmailDraft... | nothing |
| Ports | `src/groundwork/core/ports` | Interfaces to the outside world | domain |
| Services | `src/groundwork/core/services` | Pack loading, integrity check, rule extraction workflow, context assembly, rule applicability, claim checks; later harness, policies, evals runner | domain, ports |
| Adapters (driven) | `src/groundwork/adapters` | HubSpot, LanceDB, Voyage, Claude, replay, file approval | ports, vendor SDKs |
| Entrypoints (driving) | `src/groundwork/entrypoints` | CLI, HTTP API, MCP server; wire adapters into services | everything |
| Domain packs | `domains/<domain>` | Ontology schema, skills, prompts, eval scorers | data only |
| Client packs | `client_packs/<client>` | Config, fixtures, interviews, rules, golden set | data only |

The MCP server (`entrypoints/mcp_server.py`, ADR 0008) serves one pack, read-only: four thin tools over `core/services/{context,rules,claims}.py`. `wiring.build_server_context` loads the pack and builds the model only on the first claim check. Connection guide: `docs/mcp.md`.

Dependencies point inward. `core` never imports `adapters` or `entrypoints` (import-linter, checked in pre-commit and CI).

## Ports
| Port | Purpose | Adapters |
|---|---|---|
| CrmPort | Read contacts, companies, deals, products | fixture (HubSpot-shaped JSON); hubspot planned |
| MessagingPort | Send an email | console |
| ApprovalPort | Queue external emails for a human | file |
| VectorStorePort | Index and search know-how | lancedb |
| EmbeddingPort | Embed text | voyage |
| OntologyStorePort | Read and write the graph | file (JSON + networkx) |
| ModelPort | Single-shot Claude calls (extraction, judge, contextual chunking) | claude, replay |
| AgentPort | Run the drafting agent with read-only tools | claude (see ADR 0005), replay |

Adapters translate vendor formats into domain types. The core never sees HubSpot JSON or SDK objects.

The `model` key in `config.yaml` selects the adapter family (`claude` or `replay`) for ModelPort, AgentPort and EmbeddingPort. Replay serves recorded runs and never falls back to a live call.

ModelPort (`core/ports/model.py`) exposes `complete_structured`, `complete_text` and `cite` (Citations), each on a tier (`extraction` or `cheap`) that the adapter maps to a model id, so the core never names a model. `entrypoints/wiring.py` builds it: `GROUNDWORK_MODEL` overrides the config's `model`, `replay` reads `traces/<pack>/model/`, and `claude` with `GROUNDWORK_RECORD=1` is wrapped in a `RecordingModel` that writes there.

## Configuration
Each client pack selects its adapters and its domain in `client_packs/<client>/config.yaml`. Changing a SaaS is one adapter plus one line of config. Precedence: client > domain > core, through config only.

```yaml
crm: fixture        # adapter names are resolved in entrypoints/wiring.py
messaging: console
vector_store: lancedb
model: replay
domain: comms       # a folder under domains/
```

`entrypoints/wiring.py` is the composition root: the only place that maps a config name to an adapter class. An unknown name fails `validate-packs` with the list of valid names.

## Pack validation
`groundwork validate-packs` runs in pre-commit and CI. For every folder in `client_packs/` it checks the config schema, that the domain exists, that the CRM fixtures load, and `check_integrity` (`core/services/integrity.py`): dangling references (deal to contact, contact to company, deal to products) and segments or personas outside the domain vocabulary. The check goes through `CrmPort` only, so it will run unchanged against a live CRM from a manual command (CI never calls a real CRM). Each problem is printed with its pack, kind and id, for example `client_packs/acme: deal acme-d-3 references missing contact acme-c-99`. It also loads the interviews and checks `rules.yaml` and the extraction golden data (see docs/knowledge.md).

CRM fixtures live in `client_packs/<client>/fixtures/hubspot/` in HubSpot CRM v3 shape; the mapping and its simplifications are documented in `adapters/crm/hubspot_mapping.py`.

## Request flow
1. Entrypoint receives a draft and a contact id.
2. Context assembly builds a context pack (CRM facts + applicable rules + know-how passages).
3. The agent drafts the harmonized email using MCP tools.
4. `check_claims` verifies every factual claim against the ontology.
5. Policy (deterministic code, never the model) routes the result: internal and valid → MessagingPort; external → ApprovalPort; false claim → blocked.
6. The full run is written to `traces/`.

## Adding things
- New adapter: implement the port, add it to the `ADAPTERS` of `tests/contracts/test_<port>_contract.py` and pass that suite, register its name in `entrypoints/wiring.py`, reference it in a pack config.
- New client: run the playbook (docs/playbook.md); it produces the pack files.
- New domain: add `domains/<domain>` with schema, skills and scorers; no core change expected.
