# Architecture

## Layers
| Layer | Path | Contains | Depends on |
|---|---|---|---|
| Domain | `src/groundwork/core/domain` | Contact, Deal, Product, Rule, EmailDraft... | nothing |
| Ports | `src/groundwork/core/ports` | Interfaces to the outside world | domain |
| Services | `src/groundwork/core/services` | Pack loading, integrity check, rule extraction workflow, context assembly, rule applicability, claim checks, retrieval, the harmonization flow (context pack, policy engine, approvals); later evals runner | domain, ports |
| Adapters (driven) | `src/groundwork/adapters` | HubSpot, LanceDB, Voyage, Claude, replay, console messaging, file approval | ports, vendor SDKs |
| Entrypoints (driving) | `src/groundwork/entrypoints` | CLI, HTTP API, MCP server; wire adapters into services | everything |
| Domain packs | `domains/<domain>` | Ontology schema, skills, prompts, eval scorers | data only |
| Client packs | `client_packs/<client>` | Config, fixtures, interviews, rules, golden set | data only |

The MCP server (`entrypoints/mcp_server.py`, ADR 0008) serves one pack, read-only: five thin tools over `core/services/{context,rules,claims,retrieval}.py`. `wiring.build_server_context` loads the pack and its index into the vector store, and builds the model and the query embedding only on first use. Connection guide: `docs/mcp.md`.

Dependencies point inward. `core` never imports `adapters` or `entrypoints` (import-linter, checked in pre-commit and CI).

## Ports
| Port | Purpose | Adapters |
|---|---|---|
| CrmPort | Read contacts, companies, deals, products | fixture (HubSpot-shaped JSON); hubspot planned |
| MessagingPort | Send an email (only `harmonize` and `approvals` call it) | console (prints, appends to `var/outbox/`) |
| ApprovalPort | Queue external emails for a human (only `harmonize` and `approvals` call it) | file (`var/approvals/<pack>/<id>.json`) |
| VectorStorePort | Store chunks, vector and keyword search (fused in the core, ADR 0009) | lancedb, in-memory (tests) |
| EmbeddingPort | Embed documents and queries | voyage, replay |
| OntologyStorePort | Read and write the graph | file (JSON + networkx) |
| ModelPort | Single-shot Claude calls (extraction, judge, contextual chunking) | claude, replay |
| AgentPort | Run the drafting agent with read-only tools, under hard limits | claude (a tool-use loop, ADR 0005), replay (from a trace), passthrough (the draft unchanged, for demos and evals) |

Adapters translate vendor formats into domain types. The core never sees HubSpot JSON or SDK objects.

The `model` key in `config.yaml` selects the adapter family (`claude` or `replay`) for ModelPort and AgentPort; `embedding` (`voyage` or `replay`, default `replay`) selects EmbeddingPort and `vector_store` (`lancedb` or `memory`) the store. Replay serves recorded runs and never falls back to a live call.

ModelPort (`core/ports/model.py`) exposes `complete_structured`, `complete_text` and `cite` (Citations), each on a tier (`extraction` or `cheap`) that the adapter maps to a model id, so the core never names a model. `entrypoints/wiring.py` builds it: `GROUNDWORK_MODEL` overrides the config's `model`, `replay` reads `traces/<pack>/model/`, and `claude` with `GROUNDWORK_RECORD=1` is wrapped in a `RecordingModel` that writes there.

## Configuration
Each client pack selects its adapters and its domain in `client_packs/<client>/config.yaml`. Changing a SaaS is one adapter plus one line of config. Precedence: client > domain > core, through config only.

```yaml
crm: fixture        # adapter names are resolved in entrypoints/wiring.py
messaging: console
vector_store: lancedb
model: replay
domain: comms       # a folder under domains/
internal_recipient: handoffs@acme.example  # where internal emails go, never a customer
```

`entrypoints/wiring.py` is the composition root: the only place that maps a config name to an adapter class. An unknown name fails `validate-packs` with the list of valid names.

## Pack validation
`groundwork validate-packs` runs in pre-commit and CI. For every folder in `client_packs/` it checks the config schema, that the domain exists, that the CRM fixtures load, and `check_integrity` (`core/services/integrity.py`): dangling references (deal to contact, contact to company, deal to products) and segments or personas outside the domain vocabulary. The check goes through `CrmPort` only, so it will run unchanged against a live CRM from a manual command (CI never calls a real CRM). Each problem is printed with its pack, kind and id, for example `client_packs/acme: deal acme-d-3 references missing contact acme-c-99`. It also loads the interviews and checks `rules.yaml` and the extraction golden data (see docs/knowledge.md).

CRM fixtures live in `client_packs/<client>/fixtures/hubspot/` in HubSpot CRM v3 shape; the mapping and its simplifications are documented in `adapters/crm/hubspot_mapping.py`.

## Request flow (`core/services/harmonize.py`)
1. An entrypoint (`groundwork harmonize`, `POST /harmonize`, `groundwork demo`) receives a request: contact id, channel, draft.
2. `build_context_pack` assembles the contact's facts, the rules that apply and passages from the interviews, within 6000 estimated tokens. Facts are never truncated; passages go first, then the least specific rules; what was dropped is recorded in the pack.
3. The agent drafts the email. `ClaudeAgent` is a small tool-use loop (ADR 0005) whose only tools are the pack's MCP server (ADR 0008), checked allowed and read-only before the run starts. The draft, the CRM fields, the rules and the passages reach the model JSON-encoded inside `<request>`, `<crm_data>`, `<rules>` and `<passages>` blocks (`<` and `>` escaped), and the prompt says their content is data, never instructions.
4. Hard limits from the policies (steps, tokens, seconds, capped by core ceilings of 8, 60 000 and 60) abort a run with an explicit error; nothing is sent or queued.
5. `check_claims` verifies the claims of the email against the CRM.
6. `decide` (`core/services/policy.py`, pure code, never the model) routes the result: a false claim or a forbidden pattern blocks; an external email never auto-sends and goes to a human; an unknown claim goes to a human on any channel; an internal email auto-sends only when none of that fired and the policy allows it.
7. The run is written to `traces/<pack>/<case_id>.jsonl` (events `request`, `context_pack`, `step`, `output`, `claim_check`, `decision`, or `error`; no timestamps, so a rerun gives the same bytes), then the decision is acted on: send, queue in `ApprovalPort`, or nothing. `groundwork approvals approve` records the answer and sends, once.

`policies.yaml` per domain (`domains/<domain>/`) and per client pack can only add forbidden patterns, lower limits and turn internal auto-send off: any other key, or a limit above its ceiling, fails `validate-packs` naming the file. Merge order: core invariants, then domain defaults, then client.

Replay: with `model: replay` the agent is a `ReplayAgent` that serves the recorded trace of the case and refuses it (`TraceStaleError`) if the request, the system prompt or the context pack changed. Only the agent's work is replayed: the claim checks (recorded model calls) and the policy run live, so a changed policy changes the decision. `GROUNDWORK_MODEL=claude GROUNDWORK_RECORD=1 groundwork demo --model claude --record` records a pack's demo cases (a few dollars; needs both API keys).

## Adding things
- New adapter: implement the port, add it to the `ADAPTERS` of `tests/contracts/test_<port>_contract.py` and pass that suite, register its name in `entrypoints/wiring.py`, reference it in a pack config.
- New client: run the playbook (docs/playbook.md); it produces the pack files.
- New domain: add `domains/<domain>` with schema, skills and scorers; no core change expected.
