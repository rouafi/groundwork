# 0008. One read-only MCP server per pack; claims checked by code

Status: accepted

## Context
Agents and people using Claude need the same client context: CRM facts, approved rules, and a way to know whether a draft says something false. The server is reachable by a model, and the CRM holds free text written by anyone, including text that reads like instructions.

## Decision
- One server serves one client pack, chosen at start (`mcp-serve --pack`). No tool takes a client id, so a conversation cannot reach another client's data.
- Four tools, all read-only and annotated so; the registered set is pinned by a test against an allowlist. Nothing that sends or queues a message is a tool (ADR 0004).
- `check_claims` runs on the server, in two steps: the cheap model lists the claims of the text (passed as a document, untrusted), then code decides the status from the CRM. The model never decides whether a claim is true, and the calling agent does not report its own claims: a guard must not depend on the agent it guards.
- `false` only when the facts contradict the claim (price, currency, product name). What the facts cannot decide is `unknown`, for a human. Features use the same word containment as the extraction workflow (ADR 0007), so both checks share one definition and its documented limits.
- The model is built on the first claim check: the three fact tools work without an API key.
- Errors groundwork raises on purpose (unknown id, replay miss, bad vocabulary) become tool errors with their message; other exceptions stay generic so internals do not leak.

## Consequences
- A paraphrase of an allowed feature, a discount or an extra promise is `unknown`, not `false`: the policy engine (PRD-005) must route `unknown` claims to a human, not only block `false` ones.
- `check_claims` costs one cheap model call per text; with `replay` it answers only for recorded texts.
- A desktop user sees one pack per configured server; serving two clients means two entries.
