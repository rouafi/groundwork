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
- Least privilege: MCP tools are read-only except `submit_for_approval`.
- Side effects: external emails always go to `ApprovalPort`; internal auto-send only for packs whose evals pass thresholds.
- Output validation: strict output schema, then `check_claims`; a false claim blocks the email.
- Limits: max agent steps, max tokens and timeouts per run.

## Dependencies and CI
- `uv.lock` is committed; CI installs with `--frozen`.
- CI runs with read-only permissions.
- Containers run as a non-root user; mounted client packs are read-only.
