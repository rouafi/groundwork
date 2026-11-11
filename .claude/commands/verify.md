---
description: Run the verification loop (make check, then fde-reviewer) until both pass
---
Run the groundwork verification loop on the current branch. Maximum 3 iterations.

Each iteration:
1. Make sure everything is committed (`git status --porcelain` is empty). If not, commit with a Conventional Commit message.
2. Run `make check`. If it fails, fix the cause, commit, and restart the iteration.
3. Invoke the `fde-reviewer` subagent on the branch.
4. If its last line is `VERDICT: CHANGES_NEEDED`, fix every blocking item and every unmet criterion, commit, and restart the iteration.

Stop when `make check` is green and the verdict is `VERDICT: READY`. Then print the reviewer's criteria table: it goes in the PR description.

If the 3rd iteration still fails: stop, list the remaining blockers, and ask the human. Never weaken or delete a test, lower a threshold, edit the reviewer file or the hooks, or bypass hooks to get green.
