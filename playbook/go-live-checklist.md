# Go-live checklist (day 5)

Copy of this file is `client_packs/<client>/go_live.md`. Each box is ticked by a person who has
checked the point, not by the assistant. `validate-packs --stage day5` refuses a box left
unticked, and a box that is missing or reworded: keep each line exactly as it is here, and put
notes elsewhere. A box you add is held to the same rule.

## Understood
- [ ] The sponsor signed off the discovery (`discovery.yaml`, `status: signed_off`).
- [ ] The success metric has a baseline today and a target, and we know where we will read it.

## Facts and know-how
- [ ] The CRM fixtures were checked against the real system by someone who knows the data.
- [ ] Every approved rule was read by an expert; its quote and scope are right.
- [ ] Conflicts between experts were settled by a person and written down.

## Quality
- [ ] The golden set was written with the experts, and includes cases that must be blocked.
- [ ] The thresholds were agreed with the sponsor, and the evals pass on replay.
- [ ] The judge agrees with the human labels on the calibration cases.

## Safety
- [ ] `policies.yaml` was reviewed: forbidden patterns, limits, internal auto-send on or off.
- [ ] `internal_recipient` in `config.yaml` is the client's real internal address.
- [ ] External emails go to the approval queue, and it is known who approves, and how fast.
- [ ] Nothing in the pack contains a secret or real customer data that should not be there.

## Rollout and after
- [ ] Internal auto-send goes first; external stays in the queue until its approval rate is known.
- [ ] Every rejected email becomes a new golden case, and someone owns that.
- [ ] There is a way to switch the assistant off, and the sponsor knows it.
