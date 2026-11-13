# 0011. The playbook is code: templates, a scaffolder and stage checks

Status: accepted

## Context
The kit's claim is that a new client is a filled client pack, not new code, in five days. A playbook that lives in a document next to the code drifts from it: nothing tells the FDE whether day 3 is really done, and "done" means something different at each client. PRD-007 asks for the playbook to be executable.

## Decision
- **Templates are the playbook's inputs.** `playbook/` holds `discovery.template.yaml`, `config.template.yaml`, `interview-script.md` and `go-live-checklist.md`. `groundwork new-pack <client>` copies them into `client_packs/<client>/`, builds the folder aside and renames it, and never overwrites a pack. The skeleton fails every stage with precise messages until filled.
- **A day is done when a stage check says so.** `validate-packs --stage dayN` is cumulative (day 3 also needs day 1 and 2), and each problem is prefixed with its day, then the file and the field. The checks reuse the loaders and validators of the pack, so the playbook and the code cannot disagree.
- **Human actions are recorded, not performed.** The sponsor's sign-off (`DiscoveryDoc.status: signed_off` with a named `signed_off_by`), the approval of each rule and the ticks of `go_live.md` are fields a person sets. A stage fails until they are set, and neither the scaffolder, the stage checks nor the skill ever set them.
- **Day 5 holds the pack to its thresholds.** It replays the evals, whatever the environment says (never a paid call) and never accepts a pack below its own thresholds. A pack that fails its evals does not go live, even if CI tolerates it while a pack improves (`--allow-unmet-thresholds`, ADR 0010).
- **The skill drives the files, not the decisions.** `.claude/skills/client-onboarding/SKILL.md` walks the days, asks for missing inputs, writes the data and runs the stage check after each day. Tests pin that it links only files that exist, names only real commands, and never tells the model to sign off, approve or tick.

## Consequences
- Onboarding progress is a command, not a judgement. The same check runs in CI for any pack that opts in.
- The shipped packs `acme` and `beta` predate the templates: they have no `discovery.yaml` or `go_live.md`, so they pass the unstaged `validate-packs` and fail the stages until a person adds and signs them. This is deliberate: no sign-off is invented for a synthetic client.
- Day 5 evals run the full golden set on replay; for a pack with no recordings that is an explicit "recording missing" problem, which tells the FDE to record (and pay) first.
- Adding a stage rule is a code change with a test; changing what a day requires is an ADR amendment.
