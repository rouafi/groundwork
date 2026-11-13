# groundwork v0.1.0

A deployment kit for grounded AI on top of a company's SaaS tools: a reusable core, domain packs, client packs, and a 5-day playbook to fill a client pack. Demonstrated on email harmonization for two fictional clients. All data is synthetic.

## Included
- **Facts and know-how.** CRM-shaped fixtures behind a port, with integrity checks. Rules extracted from interviews by Claude, reviewed by a person, each with its provenance and scope.
- **A read-only context server (MCP)** per client pack: contact context, approved rules, product facts, a claim check and a hybrid search over the interviews. The same server feeds the agent and Claude Desktop.
- **The harness.** A context pack, a small tool-use agent on the Messages API under hard limits, a claim check, and a deterministic policy engine. External emails never send without a person's approval. Every run leaves a trace that replays.
- **Evals.** A golden set of 20 cases per client, scored by code and by a calibrated judge, with a generated report. Recorded runs replay offline, so CI needs no key.
- **The playbook as code.** Templates, `new-pack`, stage checks for each of the 5 days, and a Claude skill that walks them. The sign-off, rule approval and go-live ticks stay with people.
- `make demo` (replay, no key), `make live` (Claude and Voyage), a CLI, an HTTP API and Docker Compose.

## Not included, and known limits
- **No live CRM.** The fixtures have the shape of HubSpot data; no connector to a real system is shipped.
- **Neither synthetic pack meets all its thresholds yet.** The results table in the README is generated from the report, and says which thresholds each pack misses. They were not lowered to hide it.
- **Internal auto-send is a policy a pack can turn off; it is not gated on the evals yet.**
- The blocked case of the demo uses a stand-in agent that lets a draft through unchanged: the real models never produced such an email in the recordings. It is labelled as such.
- The HTTP API and the MCP HTTP transport have no authentication and are published on `127.0.0.1` only.
- No UI, no multi-user workflow, no package published.

## Try it
```bash
uv sync && make demo
```
