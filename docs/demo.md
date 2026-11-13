# Demo: the 20-second capture and the 3-minute video

Both show only what the repository does today, on synthetic data. Say that once, at the start. Run the demo before recording: `make demo` replays recorded runs, so what is on screen is what is in `traces/`, and nothing depends on a key or a network.

## The 20-second capture (README)
A terminal recording of `make demo`, cut to the three decisions of one client: the email that waits for a person, the one sent automatically (internal), and the one that is blocked, with the reasons printed under each. Record it with any terminal recorder (for example `vhs` or `asciinema` plus `agg`), at 100 columns, and save it as `docs/brand/demo.gif`. Then add it to the README under "See it run", and keep it in step with the output: if the capture and `make demo` disagree, record it again. Never edit a capture by hand.

## The 3-minute video: script
Plain language first. Each scene says what to show and what to say. Times are targets.

### 0:00 The problem (20 s)
Show: the README first screen.
Say: "Companies want AI on top of the tools they already use. Every project starts from zero, the know-how is in people's heads, and nobody checks what the AI writes before it reaches a customer. This kit is how a deployment team reuses most of the work from client to client."

### 0:20 One live run (60 s)
Show: `make demo` on the `acme` pack, then scroll to each decision.
Say, in this order:
1. The internal handoff is sent automatically: no false claim, no forbidden pattern.
2. The customer email goes to a person, always, and the screen shows why: one claim ("setup takes one day, so your team spends very little time getting started") is not in the product's allowed claims, so a human decides. The price in the same email was checked against the CRM and is verified.
3. The third case is blocked: the draft promises 50% off and a wrong price (400 EUR instead of 800). Say plainly that this case uses a stand-in agent that lets the draft through unchanged, to show the checks work when the model fails. In the recordings the real models never produced such an email.

The point to make: the model drafts, code decides. Nothing reaches a customer without passing checks that do not depend on the model.

### 1:20 The evals (40 s)
Show: the results table of the README, then `evals/report.md` for one pack.
Say: every client has a golden set of 20 cases, scored by code for facts, forbidden patterns, routing and traceability, and by a judge for tone, after the judge was checked against human scores. The harmonized email beats the raw draft on every measure. Then say the honest part: both packs are still below at least one of their thresholds, so neither would go live; the report says which, and the thresholds were not lowered to hide it.

### 2:00 The playbook (30 s)
Show: `uv run groundwork new-pack gamma` in a temporary folder, then `validate-packs --stage day1` failing with one message per missing field.
Say: a new client is a folder of files, filled in five days: needs, facts, know-how, golden set, go-live. Each day ends with a command that says whether it is done, and the things only a person may do (the sponsor's sign-off, rule approval, go-live ticks) stay with a person. In Claude Code, a skill walks the days.

### 2:30 At ten clients, and in Claude Desktop (30 s)
Show: the layers picture, then Claude Desktop connected to the pack's context server (docs/mcp.md).
Say: the core, the harness and the evals do not change; a new client adds a pack, which is data and configuration, not code. The same read-only context server that feeds the agent can be asked questions by a salesperson in Claude Desktop, so people and the agent share one source of truth.

## Checklist before recording
- `make check` is green and `git status` is clean.
- `make demo` output matches what you are about to say (the counts of decisions per pack).
- No `.env` or key visible in the terminal, the shell history or the window title.
- State what is not included: the data is synthetic, the CRM is fixture files in the shape of HubSpot, and no live CRM is connected.
