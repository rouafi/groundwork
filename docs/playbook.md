# Playbook: a new client in 5 days

Every step produces a validated file in `client_packs/<client>/`.

| Day | Step | Artifact | Exit criteria |
|---|---|---|---|
| 1 | Needs collection: use case, users, internal vs external, systems, success metric, risks | `discovery.yaml` | Sponsor signs off the use case and the metric |
| 2 | Facts mapping: connect the CRM, map entities to the domain schema | `config.yaml`, `facts_mapping.yaml` | Required fields mapped |
| 3 | Know-how capture: 3 to 5 expert interviews, extraction, human review | `interviews/`, `rules.yaml` | Every rule has provenance and scope |
| 4 | Golden set: 20 cases with the experts, thresholds agreed | `golden.jsonl`, `thresholds.yaml` | Level-1 evals pass |
| 5 | Go-live: policies, rollout, monitoring | `policies.yaml`, `go_live.md` | Internal auto-send and external queue live |
# x
# x
