# Security

## Secrets
- Keys only through environment variables; `.env` is git-ignored, `.env.example` documents them.
- gitleaks and detect-private-key run in pre-commit; gitleaks runs again in CI.
- Claude Code cannot read `.env` or `secrets/` (`.claude/settings.json`).

## Data
- Synthetic data only. No real customer, no real person, no real email address.
- Traces contain synthetic data only; they are safe to publish.

## LLM guardrails
- Untrusted input: CRM fields, emails and transcripts are passed as data inside clearly delimited blocks, never as instructions.
- Least privilege: every MCP tool is read-only, and the agent refuses to start if a tool it is given is not. Side effects (send, queue for approval) happen only in the `harmonize` and `approvals` services, after the policy engine decided, outside the model's control (ADR 0004); an import-linter contract pins that no other code touches `MessagingPort` or `ApprovalPort`.
- Side effects: external emails always go to `ApprovalPort` and are sent only by `groundwork approvals approve`, once; an unknown claim goes to a human on any channel; internal auto-send is a policy a pack can turn off (the evals of PRD-006 will gate it).
- Output validation: strict output schema, then `check_claims`; a false claim blocks the email.
- Limits: max agent steps, max tokens and a timeout per run, enforced by the loop and capped by core ceilings that a pack cannot raise. A run that exceeds one raises an explicit error and still leaves a trace.
- Untrusted data is JSON-encoded inside delimited blocks with `<` and `>` escaped, so a field cannot close its block. The recorded demo includes a draft that goes through a passthrough agent: the policy blocks it. In the recording runs Sonnet 5.5 ignored a discount planted in a contact's notes, and Sonnet 5.5 and Haiku 5.5 both removed an off-policy discount from a draft even when told to keep it: the model is a first layer, and the policy is a second one that does not depend on it.
- `POST /harmonize` and the MCP HTTP transport have no authentication: both are published on `127.0.0.1` only in `docker-compose.yml`.

## Dependencies and CI
- `uv.lock` is committed; CI installs with `--frozen`.
- CI runs with read-only permissions.
- Containers run as a non-root user; mounted client packs are read-only.
