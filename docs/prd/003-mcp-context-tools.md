# PRD-003: MCP context tools
Status: done | Branch: `feat/mcp-tools` | Depends on: 001, 002

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

## Implementation notes
- `ClaimCheck` carries a `reason` in addition to `{claim, kind, status, evidence}`, so a reviewer reads why a claim is `false` (for example the catalog price) without a second call.
- `check_claims` extracts claims on the server with the cheap model (the text as a document), then decides in code. The calling agent is never trusted to list its own claims (ADR 0008).
- A price is `verified` only when amount and currency both match; a price with no currency, no readable amount or no known product is `unknown`. `$` reads as USD.
- A product name must equal a catalog name (case and spacing ignored), so a nickname such as "the Pro plan" is `false` if the model reports it as a product name; the prompt asks for names as written.
- A feature with no product named is `unknown`, and the reason lists the products that allow it; the PRD's catalog-wide lookup would have verified a promise true of another product.
- With `GROUNDWORK_MODEL=claude` and no key, `check_claims` returns an error naming `ANTHROPIC_API_KEY`; API failures become `ModelError` in the Claude adapter.
- The `mcp` service is published on `127.0.0.1` only, since the server has no authentication.
- Features reuse the extraction workflow's word containment (`matching_allowed_claim`): a paraphrase stays `unknown`. No step makes a semantic judgment; the PRD-002 note said otherwise and is corrected.
- `get_rules` rejects a segment or persona outside the domain vocabulary, so a typo does not silently drop the specific rules.
- Unknown ids, replay misses and vocabulary errors come back as tool errors naming the cause. The `ping` tool is removed.
- The `mcp` service mounts `domains/` and `traces/` read-only: the image ships neither. `GROUNDWORK_PACK` picks its pack.
- Claude Desktop's documented config has no working-directory key, so `docs/mcp.md` uses `uv --directory <repo>`; `--env-file .env` keeps the API key out of the Desktop config. Checked by starting the server from `/` with a minimal PATH.
- AC5 uses the SDK's in-memory client for the tool tests, plus one stdio smoke test of the real command.

## Risks and open questions
The MCP SDK changed between v1 and v2 (`FastMCP` became `MCPServer`); read the installed package, not memory.
