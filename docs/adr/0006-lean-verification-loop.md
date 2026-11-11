# 0006. Lean verification loop

Status: accepted

## Context
Work done with Claude Code is fast but easy to over-claim: code can pass linting and still miss the PRD, or match the PRD and still be unusable by the person who deploys it at a client. A heavier setup (several reviewers, commit-bound stamps, push and CI enforcement) was considered and dropped: for a solo repo built in a few evenings it costs more time than it saves, and most of what a code reviewer would say is already enforced by lint, types, import-linter and tests.

## Decision
A change is done when `make check` is green and a single `fde-reviewer` agent, running on a different model tier than the coding session, returns READY with every PRD acceptance criterion met with evidence. `/verify` runs the loop, at most 3 iterations, then escalates to the human.

## Consequences
Fast and easy to explain. The review is advisory, not mechanically enforced: the human remains the final reviewer, and the criteria table pasted in the PR makes the check visible.
