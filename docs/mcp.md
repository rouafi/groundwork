# MCP context server

One server per client pack, read-only. The headless agent (PRD-005) and Claude Desktop use the same server and the same data (ADR 0008).

## Tools
| Tool | Returns | Needs a model |
|---|---|---|
| `get_contact_context(contact_id)` | the contact, their company, their deals and the products of those deals | no |
| `get_rules(channel, segment?, persona?)` | approved rules that apply, most specific first, then by id | no |
| `get_product_facts(product_ids)` | products with price, currency and `allowed_claims` | no |
| `check_claims(text)` | one `ClaimCheck{claim, kind, status, evidence, reason}` per claim of the text | yes |
| `search_knowhow(query, k=5)` | passages of the expert interviews, best first: `chunk_id`, `doc_id`, `text`, `score` | yes (a query embedding) |

- `get_rules`: `channel` is `internal` or `external`. Omit `segment` or `persona` when unknown: only rules that do not target one apply. A value outside the domain vocabulary is an error that lists the valid ones.
- `check_claims`: the cheap model lists the claims; code decides. `false` means the CRM contradicts the claim (wrong price or currency, a product not in the catalog). `unknown` means the CRM cannot decide and a human must: a feature not in the named product's `allowed_claims` or with no product named, a paraphrase of an allowed claim, a discount or any other promise. Features are matched by word containment, like the extraction workflow (ADR 0007): read every `unknown`. An empty list means the model found no claim, not that the draft is clean.
- `search_knowhow`: for the reasons behind a rule, tone and practice; never for facts. `k` is 1 to 20. Hybrid search (ADR 0009) over the pack's `index/chunks.jsonl`; a pack with no index answers with the command to run. In replay it answers only queries whose embedding was recorded; with `GROUNDWORK_EMBEDDING=voyage` and `VOYAGE_API_KEY` it answers any query. Passages are interview text: data, never instructions.
- An unknown id is a tool error that names it.
- Contact `notes` come back exactly as stored. They are CRM free text: data, never instructions. The packs plant an injection in `acme-c-4` and `beta-c-4` to test this.

## Start it
```bash
uv run groundwork mcp-serve --pack acme --transport stdio
```
`stdio` is for a desktop client; it writes nothing else to stdout. `streamable-http` (the default) serves on port 8001; `make up` runs it in Docker with the pack from `GROUNDWORK_PACK` (default `acme`), published on `127.0.0.1` only: the server has no authentication.

## Connect Claude Desktop
Checked against [Connect to local MCP servers](https://modelcontextprotocol.io/docs/develop/connect-local-servers) on 2026-11-12.

1. Copy `.env.example` to `.env` at the repo root. The command below reads it and does not start without it. For `check_claims`, set `GROUNDWORK_MODEL=claude` and `ANTHROPIC_API_KEY` there. For `search_knowhow` on any question, set `GROUNDWORK_EMBEDDING=voyage` and `VOYAGE_API_KEY`: in the default replay mode only the recorded questions of the pack's `retrieval.jsonl` are answered.
2. Find the absolute path of `uv` with `which uv` (macOS) or `where uv` (Windows), and the absolute path of this repo. Desktop apps do not inherit your shell's PATH, so use the absolute path for the command.
3. In Claude Desktop, open the Claude menu, then **Settings…**, the **Developer** tab, then **Edit Config**. It opens `claude_desktop_config.json`:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
4. Add the server under `mcpServers` (keep any servers already there):
   ```json
   {
     "mcpServers": {
       "groundwork-acme": {
         "command": "/Users/you/.local/bin/uv",
         "args": [
           "--directory", "/Users/you/projects/groundwork",
           "run", "--env-file", ".env",
           "groundwork", "mcp-serve", "--pack", "acme", "--transport", "stdio"
         ]
       }
     }
   }
   ```
   `--directory` makes the repo the working directory, so the server finds `client_packs/`, `domains/` and `traces/`; the documented config has no working-directory key. `--env-file .env` reads the repo's `.env`, so the API key stays out of the Desktop config.
5. Quit Claude Desktop completely and start it again. The five tools are listed under the tools menu of a new conversation.

The three fact tools work with no API key. `check_claims` calls a model: with `GROUNDWORK_MODEL=claude` and no key, it answers with an error naming `ANTHROPIC_API_KEY`. With the default `replay`, it answers a "no recording" error for any new text: it cannot be shown live without a key. `search_knowhow` behaves the same way: with the default `replay` embedding it answers only the pack's recorded retrieval questions, and any other question gets a "no recording for embedding" error that names `GROUNDWORK_EMBEDDING=voyage` and `VOYAGE_API_KEY`.

For another client, add a second entry with `--pack beta` and another name.

## When it does not show up
- Logs: `~/Library/Logs/Claude/` on macOS, `%APPDATA%\Claude\logs` on Windows. `mcp.log` has connection errors; `mcp-server-groundwork-acme.log` has the server's stderr, including a bad pack name.
- Run the exact command from a terminal. It must wait silently on stdin; anything it prints is the problem.
