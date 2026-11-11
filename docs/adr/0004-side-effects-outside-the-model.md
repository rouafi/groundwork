# 0004. Side effects stay outside the model

Status: accepted

## Context
The agent drafts emails from CRM records, interview transcripts and free text, all of which can contain instructions aimed at the model (prompt injection). An agent that can send or queue emails can be manipulated into doing so.

## Decision
The model only has read-only tools. Routing and sending are done by deterministic code: a policy engine decides `auto_send`, `approval` or `blocked` after claims are checked. Some invariants are not configurable by packs: external emails never auto-send, and any false claim blocks. Packs may only tighten policies.

## Consequences
The agent cannot cause harm on its own. It is less "agentic" than a design where the model submits its own output. Policies are testable without calling a model.
