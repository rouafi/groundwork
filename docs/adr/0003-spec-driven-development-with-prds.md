# 0003. Spec-driven development with PRDs

Status: accepted

## Context
AI-assisted coding drifts without an explicit contract, and large pull requests are hard to review. The repo is also a portfolio piece: its history must read as a sequence of deliberate, reviewable steps.

## Decision
Every pull request implements one PRD from `docs/prd/`. A PRD states the goal, scope (in and out), interfaces and data formats, numbered acceptance criteria and a commit plan. Claude Code reads the PRD, restates the plan, waits for approval, follows the commit plan and ticks the acceptance criteria. The `fde-reviewer` agent checks the outcome against the PRD (ADR 0006). The index in `docs/prd/README.md` tracks status.

## Consequences
Upfront writing cost, in exchange for scope control, a readable history and checkable work. A PRD may be amended inside its own PR when reality differs, with a note; it is never ignored silently.
