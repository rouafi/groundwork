# Security policy

## Scope
This repository is a demonstration kit. All data in it is synthetic: no real customer, person or email address, no real credentials. It is not a hosted service and there is no production deployment to attack.

In scope: a flaw in the code or configuration that would let an agent, a CRM record, an email or an interview transcript cause an action the policy engine should have stopped (for example an external email sent without approval, or an instruction in untrusted data being obeyed), a secret committed to the repository, or a vulnerable dependency.

Out of scope: findings that need a real key or a real CRM, the unauthenticated `POST /harmonize` and MCP HTTP endpoints when exposed beyond `127.0.0.1` (they are published on localhost only in `docker-compose.yml`, see [docs/security.md](docs/security.md)), and the known gap that the demo's thresholds are not met yet (see the results in the README).

## Reporting a vulnerability
Please do not open a public issue with the details. Use GitHub's private vulnerability reporting: the **Security** tab of this repository, then **Report a vulnerability**. If that option is not available, open an issue that says only that you have a security report and asks how to reach the maintainer, without the details.

Include what you found, how to reproduce it on a clean clone (`uv sync`, then the commands), and what you expected. Reports are read on a best-effort basis: this is a personal project, with no service level.

## Supported versions
Only the latest commit of `main` and the latest release.

## What the project already does
Keys only through environment variables, secret scanning in pre-commit and CI, read-only agent tools, side effects only after the policy engine decides, and a human approval for every external email: see [docs/security.md](docs/security.md).
