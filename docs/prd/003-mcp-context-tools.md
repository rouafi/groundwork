# PRD-003: MCP context tools
Status: todo | Branch: `feat/mcp-tools` | Depends on: 001, 002

## Goal
Expose the client's context to any agent through a read-only MCP server: facts, applicable rules, product facts, and claim checking.

## Why
This is the "shared context" claim made concrete: the headless agent and Claude Desktop use the exact same server and the same data.

## Read first
CLAUDE.md, docs/architecture.md, docs/security.md, docs/knowledge.md.

## Scope
In: four tools, the services behind them, server wiring per pack, Claude Desktop connection doc.
Out: `search_knowhow` (004), any tool with a side effect, the agent loop (005).

## Design
**Tools** (thin wrappers in `entrypoints/mcp_server.py`; logic in `core/services/`, pure functions of ports):
| Tool | Returns |
|---|---|
| `get_contact_context(contact_id)` | `{contact, company, deals, products}` |
| `get_rules(channel, segment=None, persona=None)` | approved rules that apply, most specific first, then by id |
| `get_product_facts(product_ids)` | products with `allowed_claims` |
| `check_claims(text)` | list of `ClaimCheck{claim, kind, status, evidence}` |

All outputs are typed Pydantic models. Every tool is read-only. `submit_for_approval` is deliberately not a tool: routing and sending are done by the policy engine in PRD-005, outside the model's control (see ADR 0004).

**Rule applicability**: a rule applies when it is `approved`, its channel is `any` or equals the requested channel, and its `segments` and `personas` are empty or contain the requested value. Specificity = number of non-empty scope dimensions (channel counts if not `any`).

**check_claims**: step 1, `ModelPort.complete_structured` extracts claims as `{text, kind: price|product_name|feature|other, product_id, value}`. Step 2 is deterministic:
- `price`: normalized amount and currency equal the product's price, else `false`
- `product_name`: the name exists in the catalog, else `false` (fabricated product)
- `feature`: the claim matches an `allowed_claims` entry (normalized), else `unknown`
- `other`: `unknown`
Status is `verified | false | unknown`; `evidence` holds the id of the supporting node.

**Server wiring**: `groundwork mcp-serve --pack acme [--transport stdio|streamable-http]`. The pack is fixed at start; tools never take a client id. Use the current `mcp` v2 API (`MCPServer`). Update `docker-compose.yml` so the `mcp` service passes `--pack` from an env var.

**docs/mcp.md**: how to connect to Claude Desktop with the stdio transport (command `uv`, args `run groundwork mcp-serve --pack acme --transport stdio`, working directory = repo root). Verify the config format against the current Claude Desktop MCP documentation before writing it.

## Files
`core/services/{context,rules,claims}.py`, `core/domain/claims.py`, `entrypoints/{mcp_server,cli,wiring}.py`, `docs/mcp.md`, `docker-compose.yml`, tests.

## Acceptance criteria
1. A test asserts the registered tool names are a subset of an explicit allowlist and that none writes anything.
2. The rule-applicability matrix (channel x segment x persona, including empty scopes) is covered by parametrized unit tests.
3. `check_claims` marks a wrong price `false`, a fabricated product `false`, an unlisted feature `unknown`, a correct price `verified` (stub `ModelPort`).
4. The contact whose `notes` field holds the injection string is returned as data, unmodified, inside the `notes` field; no tool treats it as an instruction (test).
5. The server starts on stdio and answers a tool call in an integration test; if the SDK offers an in-memory client use it, otherwise add one stdio smoke test.
6. Following `docs/mcp.md` by hand, Claude Desktop lists the four tools (manual check, noted in the PR).

## Tests
Unit: services and claim verification. Integration: server round trip. Security: injection-as-data test.

## Commit plan
1. `feat(domain): add claim check types`
2. `feat(knowledge): add rule applicability and ordering service`
3. `feat(mcp): add context assembly service for contact facts`
4. `feat(knowledge): add claim extraction and deterministic verification`
5. `feat(mcp): expose context tools on the MCP server`
6. `feat(cli): add mcp-serve with pack and transport options`
7. `docs: add MCP connection guide and mark PRD-003 done`

## Risks and open questions
The MCP SDK changed between v1 and v2 (`FastMCP` became `MCPServer`); read the installed package, not memory.
