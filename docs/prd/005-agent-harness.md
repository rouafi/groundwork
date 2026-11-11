# PRD-005: Agent harness, policies and traces
Status: todo | Branch: `feat/agent-harness` | Depends on: 001, 002, 003

## Goal
Run the full email harmonization flow: context pack, agent drafts, claims are checked, a deterministic policy routes the result, everything is traced and replayable.

## Why
This is the harness: the part that makes an agent safe to deploy at a client. The model drafts; code decides.

## Read first
CLAUDE.md, docs/architecture.md, docs/security.md, docs/adr/0004-side-effects-outside-the-model.md.

## Scope
In: agent port and adapters, context assembly, policy engine, messaging and approval adapters, traces, CLI, HTTP endpoint, `demo` command.
Out: webhooks, auth, UI, multi-tenant serving.

## Design
**Step 0, spike (before any code)**: read the current Claude Agent SDK documentation for Python: how tools and MCP servers are attached, how a structured final output is obtained, whether the runtime is bundled, impact on the Docker image. Record the result in `docs/adr/0005-agent-runtime.md`. If unsuitable, implement a hand-written tool-use loop on the Messages API (about 100 lines) behind the same port, and say so in the ADR.

**Types** (`core/domain/harmonize.py`): `HarmonizeRequest(contact_id, channel, draft)`, `ContextPack(contact_context, rules, passages, estimated_tokens, truncated)`, `HarmonizedEmail(subject, body, rationale, cited_nodes)`, `AgentStep(tool, arguments, result_summary)`, `AgentResult(email, steps, usage)`, `Decision(route: auto_send|approval|blocked, reasons)`.

**Ports**: `AgentPort.run(*, system, context, request) -> AgentResult`; `MessagingPort.send(email, contact)`; `ApprovalPort.submit(item) -> id`, `list_pending()`, `resolve(id, approved, reason)`.

**Adapters**: `ClaudeAgent` (per ADR 0005, attaches the pack's MCP server), `ReplayAgent` (loads the recorded trace for the case id; claim checks and policy are recomputed live, only model calls are replayed), `ConsoleMessaging` (prints and appends to `var/outbox/<pack>.jsonl`), `FileApproval` (`var/approvals/<pack>/<id>.json`, status pending/approved/rejected, rejection reason stored). The config key `model` selects the adapter family (`claude` or `replay`) for `ModelPort`, `AgentPort` and `EmbeddingPort`. Add `var/` to `.gitignore`.

**Context assembly** (`core/services/context_pack.py`): budget default 6000 estimated tokens (`len(text) / 4`, deterministic). Priority: contact facts, then products referenced by deals, then rules (most specific first), then passages. Truncate passages first, then the least specific rules; never truncate facts. Record what was dropped in `truncated`.

**Prompt** `domains/comms/prompts/harmonize.md`: CRM data, rules and passages are wrapped in `<crm_data>`, `<rules>`, `<passages>`; the prompt states that their content is data and never instructions. Output must match the `HarmonizedEmail` schema and cite node ids.

**Policy engine** (`core/services/policy.py`, pure code, no model): `decide(email, claim_checks, channel, policies) -> Decision`.
- Any claim with status `false` gives `blocked`.
- Any `forbidden_patterns` regex match for the channel gives `blocked`.
- `external` never gives `auto_send`; a valid external email gives `approval`.
- `internal` gives `auto_send` only if nothing above fired and `auto_send_internal` is true.
- These invariants are not configurable. A pack's `policies.yaml` may add patterns, lower limits, and turn internal auto-send off; validation rejects any attempt to weaken an invariant.
- Precedence: core invariants, then domain defaults, then client overrides (merge function with unit tests, including `beta`'s tone override).
- `policies.yaml`: `forbidden_patterns: {internal: [...], external: [...]}`, `limits: {max_steps, max_tokens, timeout_s}`, `auto_send_internal`. Core ceilings cap the limits (defaults 8 steps, 60 s).

**Traces**: `traces/<pack>/<case_id>.jsonl`, one event per line, types `request, context_pack, step, output, claim_check, decision`, no timestamps (stable diffs). `case_id` is given or the first 12 hex characters of the request hash.

**Entrypoints**: `groundwork harmonize --pack acme --contact c_001 --channel external --draft draft.txt`; `groundwork approvals list|approve|reject`; `POST /harmonize` (pack from `GROUNDWORK_PACK`) returning `{email, decision, trace_id}`; `groundwork demo [--pack] [--model claude --record]` runs the demo cases (3 per client taken from the golden set once PRD-006 lands; until then a `demo_cases.json` in each pack) and prints raw draft, harmonized email and decision.

## Files
`core/domain/harmonize.py`, `core/ports/{agent,messaging,approval}.py`, `core/services/{context_pack,policy,harmonize}.py`, `adapters/{agent,messaging,approval}/...`, `domains/comms/prompts/harmonize.md`, `client_packs/*/policies.yaml`, `entrypoints/{cli,api,wiring}.py`, `docs/adr/{0005-agent-runtime}.md`, tests.

## Acceptance criteria
1. With a scripted fake agent: internal and valid gives `auto_send`; external and valid gives `approval`; external with a wrong price gives `blocked`; an email matching a forbidden pattern gives `blocked`.
2. A pack config cannot make an external email auto-send (test of the invariant through `policies.yaml`).
3. For the injection contact, the drafted email contains no discount, or the policy blocks it with an explicit reason (test on the recorded or scripted output).
4. Exceeding `max_steps` or the timeout aborts the run with an explicit error and sends nothing.
5. `make demo` works with no environment variables, replays recorded traces, and shows the three routes.
6. Every run writes a trace that `ReplayAgent` can replay to the same decision.
7. The agent cannot cause a side effect: no tool exposed to it writes, and `MessagingPort` and `ApprovalPort` are only called from `policy`/`harmonize` services.

## Tests
Unit: context assembly and truncation, policy matrix, policy merge, invariants. Contract: `ApprovalPort`, `MessagingPort`. Integration: full pipeline with a scripted agent, replay over committed traces, API round trip.

## Commit plan
1. `docs(adr): record agent runtime decision after SDK spike`
2. `feat(domain): add harmonization types and decision model`
3. `feat(harness): add context pack assembly with token budget`
4. `feat(harness): add deterministic policy engine with invariants`
5. `feat(ports): add agent, messaging and approval ports`
6. `feat(adapters): add console messaging and file approval`
7. `feat(adapters): add Claude agent and replay agent`
8. `feat(harness): add harmonize service with traces`
9. `feat(cli): add harmonize, approvals and demo commands`
10. `feat(api): add POST /harmonize`
11. `feat(packs): add policies and recorded demo traces`
12. `docs: update architecture and security, mark PRD-005 done`

## Risks and open questions
Recorded traces require one live run per pack. If no API key is available, stop and ask. The SDK spike may change the adapter, never the port or the policy engine.
