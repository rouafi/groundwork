# 0005. The agent is a small tool-use loop on the Messages API

Status: accepted

## Context
The harness needs an agent that drafts an email with read-only tools, under hard limits (steps, tokens, time), and whose every run can be recorded and replayed. PRD-005 asks for a spike on the Claude Agent SDK for Python first, and allows a hand-written loop if the SDK does not fit. Spike done on 2026-11-12, SDK `claude-agent-sdk` 0.2.180, from its documentation and a throwaway install outside the project.

What the SDK offers: an MCP server (stdio, HTTP or in-process) attached by name, built-in tools switched off with `tools=[]`, only the passed servers with `strict_mcp_config`, `max_turns` and `max_budget_usd`, a JSON-schema `output_format` returned as `ResultMessage.structured_output`, and typed errors (`error_max_turns`, budget).

What it costs:
- It drives a bundled Claude Code CLI as a subprocess. The wheel is 134 MB, and the bundled binary is 324 MB once installed, on top of a project environment that is already 580 MB (LanceDB, Arrow). The image grows by more than half for one adapter.
- The subprocess is a whole coding agent: its own system prompt, settings discovery (`setting_sources`), a home directory it writes to, and an `atexit` cleanup of children. Each of these is a surface to switch off for a client-facing harness, and the non-root image needs a writable home.
- Our limits would be the SDK's: turns and budget, not tokens per run or a wall-clock timeout, which we would add around it.
- The model calls happen inside the subprocess, so a recording can only be taken at the level of steps, never by the `ModelPort` machinery the repo already has.

## Decision
`ClaudeAgent` is a loop of about a hundred lines on the Messages API, behind `AgentPort`:
- The tools are the pack's own MCP server (`create_server`), reached with an in-memory MCP client, so the agent sees exactly the five read-only tools of ADR 0008 and nothing else. A test pins that the tool list it can call is a subset of `ALLOWED_TOOLS`.
- The loop owns the limits: `max_steps`, a token budget from the reported usage, and a wall-clock timeout. Exceeding one raises an explicit error and nothing is sent.
- The final answer must validate against the `HarmonizedEmail` schema; a refusal or an invalid answer is an error, never a partial email.
- Every step (tool, arguments, result summary) and the usage are returned in `AgentResult` and written to the trace, so `ReplayAgent` replays a run from its trace.

Nothing else in the design depends on this choice: the port, the context pack, the policy engine and the traces are the same with any runtime.

## Consequences
- We maintain a small loop instead of depending on a 324 MB runtime; the image stays slim and starts fast.
- Limits and recordings are exact and testable without a model.
- We do not get the SDK's built-in features (sessions, hooks, sub-agents). The harness does not need them.
- If a client needs them, an SDK-backed `AgentPort` adapter can be added beside this one without touching the port or the policy engine. Revisit if the bundled runtime shrinks or the loop grows past a few hundred lines.
- `CLAUDE.md` still lists the Claude Agent SDK in the stack line; it is not used at this point.
