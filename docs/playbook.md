# Playbook: a new client in 5 days

Every step produces files in `client_packs/<client>/`, and a command says whether the day is done. The playbook is how the pack gets its inputs: see [ADR 0011](adr/0011-playbook-is-code.md).

```bash
uv run groundwork new-pack <client> --domain comms          # the skeleton, from playbook/
uv run groundwork validate-packs --pack <client> --stage day1   # and day2 ... day5
```

A stage is cumulative: `day3` also checks days 1 and 2. Each problem starts with its day, then the file and the field, for example `client_packs/gamma: day1: discovery.yaml: sponsor: String should have at least 1 character`. In Claude Code, the `client-onboarding` skill (`.claude/skills/client-onboarding/`) walks the days with you; it writes the data and runs the check, and leaves the human actions below to people.

| Day | Step | Artifact | `--stage` passes when |
|---|---|---|---|
| 1 | Needs collection: use case, users, internal vs external, systems, success metric, risks | `discovery.yaml` ([template](../playbook/discovery.template.yaml)) | the file is valid and the sponsor signed it off |
| 2 | Facts: the CRM export and the pack config | `config.yaml`, `fixtures/` | the config is valid, the fixtures load and agree, none is empty |
| 3 | Know-how: 3 to 5 expert interviews ([script](../playbook/interview-script.md)), extraction, human review | `interviews/`, `rules.yaml` | at least 3 interviews, an approved rule, every rule with provenance and scope |
| 4 | Golden set and thresholds, written with the experts | `golden.jsonl`, `thresholds.yaml`, `rubric.md`, `judge_calibration.jsonl` | at least 20 cases for known contacts, thresholds, rubric and a calibration set |
| 5 | Go-live: policies, checklist ([template](../playbook/go-live-checklist.md)), recorded evals | `policies.yaml`, `go_live.md` | policies load, every box is ticked, and the evals pass their thresholds on replay |

## What only a person does
No script and no assistant does these for you; a stage fails until they are recorded.
- **Day 1:** the sponsor signs off the use case and the metric (`status: signed_off`, `signed_off_by`).
- **Day 3:** an expert reviews the proposals of `extract-rules` and approves each rule in `rules.yaml`.
- **Day 4:** the experts and the sponsor agree the thresholds. A threshold is never lowered to pass.
- **Day 5:** a person ticks each box of `go_live.md`, after checking the point.

## Notes
- `extract-rules`, `index` and `evals --model claude --record` call paid APIs. Run them knowingly; the stage checks themselves never do (day 5 replays).
- Day 5 needs recorded runs for the golden set in `traces/<client>/`. Without them it says what is missing.
- The shipped packs `acme` and `beta` have no `discovery.yaml` or `go_live.md` (nobody signs for a synthetic client), so the stages fail on them by design. The unstaged `validate-packs` is what CI runs.
- Never create a real client pack in this repository: the tests scaffold one in a temporary folder.
