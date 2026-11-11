# Architecture

## Layers
| Layer | Path | Contains | Depends on |
|---|---|---|---|
| Domain | `src/groundwork/core/domain` | Contact, Deal, Product, Rule, EmailDraft... | nothing |
| Ports | `src/groundwork/core/ports` | Interfaces to the outside world | domain |
| Services | `src/groundwork/core/services` | Harness, context assembly, policies, evals runner | domain, ports |
| Adapters (driven) | `src/groundwork/adapters` | HubSpot, LanceDB, Voyage, Claude, replay, file approval | ports, vendor SDKs |
| Entrypoints (driving) | `src/groundwork/entrypoints` | CLI, HTTP API, MCP server; wire adapters into services | everything |
| Domain packs | `domains/<domain>` | Ontology schema, skills, prompts, eval scorers | data only |
| Client packs | `client_packs/<client>` | Config, fixtures, interviews, rules, golden set | data only |

Dependencies point inward. `core` never imports `adapters` or `entrypoints` (import-linter, checked in pre-commit and CI).

## Ports
| Port | Purpose | Adapters |
|---|---|---|
| CrmPort | Read contacts, companies, deals, products | fixture, hubspot |
| MessagingPort | Send an email | console |
| ApprovalPort | Queue external emails for a human | file |
| VectorStorePort | Index and search know-how | lancedb |
| EmbeddingPort | Embed text | voyage |
| OntologyStorePort | Read and write the graph | file (JSON + networkx) |
| ModelPort | Single-shot Claude calls (extraction, judge, contextual chunking) | claude, replay |
| AgentPort | Run the drafting agent with read-only tools | claude (see ADR 0005), replay |

Adapters translate vendor formats into domain types. The core never sees HubSpot JSON or SDK objects.

The `model` key in `config.yaml` selects the adapter family (`claude` or `replay`) for ModelPort, AgentPort and EmbeddingPort. Replay serves recorded runs and never falls back to a live call.

## Configuration
Each client pack selects its adapters in `client_packs/<client>/config.yaml`. Changing a SaaS is one adapter plus one line of config. Precedence: client > domain > core, through config only.

## Request flow
1. Entrypoint receives a draft and a contact id.
2. Context assembly builds a context pack (CRM facts + applicable rules + know-how passages).
3. The agent drafts the harmonized email using MCP tools.
4. `check_claims` verifies every factual claim against the ontology.
5. Policy (deterministic code, never the model) routes the result: internal and valid → MessagingPort; external → ApprovalPort; false claim → blocked.
6. The full run is written to `traces/`.

## Adding things
- New adapter: implement the port, pass `tests/contracts/<port>`, reference it in a pack config.
- New client: run the playbook (docs/playbook.md); it produces the pack files.
- New domain: add `domains/<domain>` with schema, skills and scorers; no core change expected.
