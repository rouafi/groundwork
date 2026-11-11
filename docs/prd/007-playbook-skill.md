# PRD-007: Playbook and onboarding skill
Status: todo | Branch: `feat/playbook-skill` | Depends on: 006

## Goal
Make the 5-day client playbook executable: templates, a pack scaffolder, stage-based validation, and a Claude skill that runs the onboarding with the FDE.

## Why
The playbook must produce files the code consumes, not a document next to the code. This is the "repeatable, not one-off" claim.

## Read first
CLAUDE.md, docs/playbook.md, docs/architecture.md.

## Scope
In: discovery schema and template, interview script, go-live checklist, `new-pack`, `validate-packs --stage`, the skill.
Out: a UI, CRM provisioning, multi-user workflow.

## Design
**Templates** in `playbook/`: `discovery.template.yaml`, `interview-script.md`, `go-live-checklist.md`.

**DiscoveryDoc** (`core/domain/discovery.py`): `client`, `sponsor`, `use_case`, `users`, `channels`, `systems[{name, role}]`, `success_metric{name, baseline, target}`, `risks`, `status: draft|signed_off`, `signed_off_by`.

**`groundwork new-pack <client> --domain comms`** creates `client_packs/<client>/` from templates (config, discovery, empty folders). The skeleton fails validation with precise messages until filled.

**`validate-packs --stage dayN`**:
| Stage | Required |
|---|---|
| day1 | `discovery.yaml` valid and `signed_off` |
| day2 | `config.yaml` valid, fixtures load and are consistent |
| day3 | at least 3 interviews, `rules.yaml` with approved rules and valid provenance |
| day4 | `golden.jsonl` with at least 20 cases, `thresholds.yaml`, `judge_calibration.jsonl` |
| day5 | `policies.yaml`, `go_live.md` with every checkbox ticked, evals passing |

**Skill** `.claude/skills/client-onboarding/SKILL.md` (frontmatter `name`, `description`): walks day by day, asks for the missing inputs, writes the artifacts, runs `validate-packs --stage dayN` after each step, and stops when a stage fails. It never marks `signed_off` or approves rules itself; those stay human actions. Keep the SKILL.md short and link the templates.

## Files
`core/domain/discovery.py`, `entrypoints/cli.py`, `playbook/*`, `.claude/skills/client-onboarding/SKILL.md`, `docs/playbook.md`, tests.

## Acceptance criteria
1. `new-pack gamma --domain comms` creates a skeleton; `validate-packs --stage day1` fails with messages naming each missing field (test in a temp dir).
2. Filling and signing off the discovery file makes day1 pass; breaking it makes it fail again.
3. Each stage's checks are covered by a unit or integration test.
4. The skill file passes a lint of frontmatter (name, description present) and references only files that exist (test).
5. The skill never contains an instruction to set `signed_off` or `approved` on behalf of a human (test that greps for it).

## Tests
Unit: DiscoveryDoc validation, stage checks. Integration: scaffold then validate by stage in a temp dir.

## Commit plan
1. `feat(domain): add discovery document schema`
2. `feat(playbook): add discovery template, interview script and go-live checklist`
3. `feat(cli): add new-pack scaffolder`
4. `feat(cli): add stage-based pack validation`
5. `feat(claude): add client-onboarding skill`
6. `docs: align playbook with executable stages and mark PRD-007 done`

## Risks and open questions
Do not create a real third client pack in the repo; the scaffolder is tested in a temp dir. A short screen capture of the skill on a throwaway pack is welcome for PRD-008.
