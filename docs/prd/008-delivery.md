# PRD-008: Delivery, README v2, demo and release
Status: todo | Branch: `docs/delivery` | Depends on: 006

## Goal
Make the repo understandable in 60 seconds by a non-engineer and verifiable in a minute by an engineer, then release it.

## Why
The README and the demo are what a hiring manager actually sees. A recruiter reads the first screen and the results table.

## Read first
README.md, docs/evals.md, evals/report.md.

## Scope
In: README restructure, results block, demo capture, video script, repo metadata, security policy, release.
Out: marketing site, blog post, package publication.

## Design
**README structure** (top to bottom): logo and one-line promise; "In 30 seconds" (plain language, no jargon); demo GIF with a link to the 3-minute video; results table; the 5-day playbook; the layers diagram; "For engineers" (ontologies, request flow, ports, Swap any SaaS, repo layout); development; license. State clearly that all data is synthetic.

**In 30 seconds text**: companies want AI on top of their SaaS tools, but every project starts from zero; this kit lets a forward-deployed team reuse most of the work across clients and customize only the last part through a 5-day playbook; the demo harmonizes sales emails on HubSpot for two clients, with checks before anything is sent.

**Results block**: generated, never typed. A script injects the summary of `evals/report.md` between `<!-- results:start -->` and `<!-- results:end -->` (`make readme-results`); a check in `make check` fails if the block is stale.

**Demo**: a 20-second GIF of `make demo` (recorded with a terminal recorder), and a 3-minute video script in `docs/demo.md`: problem, one live run, evals, playbook, how a team deploys it at 10 clients, same MCP server in Claude Desktop.

**Repo metadata**: description, topics, social preview image (1280x640 built from the logo), pinned on the profile. `SECURITY.md` (how to report, scope: synthetic demo). Tag `v0.1.0` with release notes listing what is and is not included.

## Files
`README.md`, `docs/demo.md`, `docs/brand/social-preview.png`, `SECURITY.md`, `scripts/readme_results.py`, `Makefile`, tests.

## Acceptance criteria
1. In a clean clone with no environment variables, `uv sync && make demo` succeeds in under 60 seconds.
2. The results block matches `evals/report.md`; a stale block fails CI (test).
3. All relative links and images in README and docs resolve (test).
4. A person outside engineering can say, after reading the first screen, what the project does (checked with one reader, noted in the PR).
5. `v0.1.0` is tagged and the release notes are published.

## Tests
Unit: results injection, link check. Integration: clean-clone demo in CI.

## Commit plan
1. `feat(scripts): add README results injection and staleness check`
2. `docs: restructure README with plain-language summary and results block`
3. `docs: add demo capture and video script`
4. `docs: add security policy and social preview`
5. `docs: mark PRD-008 done and prepare v0.1.0 release notes`

## Risks and open questions
Never write numbers in the README by hand. If the demo GIF and the report disagree, regenerate both from a fresh run.
