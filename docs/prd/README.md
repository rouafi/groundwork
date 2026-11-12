# Product requirements (PRDs)

One PRD per pull request. A PRD is the contract between the plan and the code: Claude Code implements it, the `fde-reviewer` agent checks the outcome against it.

## How to use a PRD (humans and Claude Code)
1. Read the PRD fully, plus every doc listed under "Read first".
2. Restate the plan and the commit list. Wait for approval before writing code.
3. Work on the PRD's branch and follow its commit plan, one logical change per commit.
4. Do not widen the scope. Anything under "Out of scope" becomes a new PRD or an issue.
5. If reality contradicts the PRD, amend the PRD in the same PR with a short note. Never deviate silently.
6. Tick every acceptance criterion in the PR description, with evidence (test name or command output).
7. In the last commit of the PR, set the PRD status to `done` in the index below.

## Standard definition of done (applies to every PRD)
- `make check` is green at every commit, not only at the last one
- New behavior is tested; coverage of `groundwork.core` stays at or above 90%
- Docs under `docs/` are updated; an ADR is added for any decision the PRD did not already settle
- No secrets, no real data; `traces/` and `evals/report.md` are never edited by hand
- `/verify` ends with `make check` green and `fde-reviewer` READY, every acceptance criterion met with evidence (docs/workflow.md)

## Index
| ID | Title | Branch | Depends on | Status |
|---|---|---|---|---|
| [001](001-facts-domain.md) | Facts domain and CRM port | `feat/facts-domain` | none | done |
| [002](002-knowhow-ontology.md) | Know-how ontology and rule extraction | `feat/knowhow-ontology` | 001 | done |
| [003](003-mcp-context-tools.md) | MCP context tools | `feat/mcp-tools` | 001, 002 | done |
| [004](004-vector-search.md) | Vector search for know-how | `feat/vector-search` | 002 | done |
| [005](005-agent-harness.md) | Agent harness, policies and traces | `feat/agent-harness` | 001, 002, 003 | todo |
| [006](006-evals.md) | Evals, golden sets and report | `feat/evals` | 005 | todo |
| [007](007-playbook-skill.md) | Playbook and onboarding skill | `feat/playbook-skill` | 006 | todo |
| [008](008-delivery.md) | Delivery: README v2, demo, release | `docs/delivery` | 006 | todo |

## Order and cut line
Run in numeric order. If time runs short, cut in this order: 004 first (everything else works without it), then the optional parts of 007. Never cut `check_claims` (003), the policy engine (005) or the evals (006).

## Template
```
# PRD-NNN: Title
Status: todo | Branch: ... | Depends on: ...
## Goal
## Why
## Read first
## Scope (in / out)
## Design (interfaces, data formats, rules)
## Files
## Acceptance criteria (numbered, testable)
## Tests
## Commit plan
## Risks and open questions
```
