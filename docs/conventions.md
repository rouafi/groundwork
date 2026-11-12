# Conventions

## Branches
Trunk-based. `main` is always green and protected (CI required). Short-lived branches: `feat/...`, `fix/...`, `docs/...`, `chore/...`.

## Commits (Conventional Commits, enforced by a commit-msg hook)
Format: `type(scope): imperative summary` (72 chars max), then a body explaining why.
- Types: feat, fix, refactor, test, docs, build, ci, chore, perf, revert
- Scopes: domain, ports, adapters, harness, mcp, evals, knowledge, packs, cli, api, docs, ci, deps
- One logical change per commit. Each commit builds and passes tests on its own.
- No "WIP", no "fix typo" chains: amend or squash locally before pushing.

Examples:
- `feat(ports): add CrmPort and domain types for contacts and deals`
- `feat(adapters): add fixture CRM adapter backed by HubSpot-shaped JSON`
- `test(contracts): run CrmPort suite against fixture adapter`
- `docs(adr): record ontology for facts, vectors for know-how`

## Pull requests
- Small (under ~400 changed lines), one topic, template filled in.
- CI green, and `/verify` passed (`fde-reviewer` READY); paste its criteria table in the description.
- Merge with "Rebase and merge" so meaningful commits stay visible on `main`.

## Tests
| Marker | What | Runs |
|---|---|---|
| unit | Pure logic, no I/O beyond tmp_path | pre-commit, CI |
| contract | Same suite for every adapter of a port | pre-commit, CI |
| integration | Real wiring (CLI, API, MCP, LanceDB), no paid API | pre-push, CI |
| live | Real Claude, Voyage, HubSpot | manual only |

Coverage is measured on `groundwork.core`.

## Lint and types
ruff (lint incl. bandit security rules, and format), mypy strict, import-linter for architecture rules.

## Definition of done
`make check` green, behavior tested, every document that describes the change updated in the same PR (the ADR added or amended, the PRD's status and notes, `docs/*.md`, the README, `CLAUDE.md`), `fde-reviewer` READY with every PRD acceptance criterion met with evidence. See docs/workflow.md.
