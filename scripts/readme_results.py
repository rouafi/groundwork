"""Keep the results block of the README in step with evals/report.md.

The numbers in the README are never typed: this script copies the summary and the
before-and-after tables out of the generated report, between two markers.

    uv run python scripts/readme_results.py           # rewrite the block
    uv run python scripts/readme_results.py --check   # exit 1 if the block is stale
"""

import argparse
import re
import sys
from pathlib import Path

START = "<!-- results:start -->"
END = "<!-- results:end -->"
REPORT = Path("evals/report.md")
README = Path("README.md")


class ResultsError(Exception):
    """The report or the README is not in the shape this script relies on."""


def _section(text: str, heading: str) -> str:
    """The body of a markdown section: from its heading to the next heading of any level."""
    match = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^#{{1,6}} |\Z)", text, re.M | re.S)
    if match is None:
        raise ResultsError(f"{REPORT}: no section {heading!r}")
    return match.group(1).strip()


def build_block(report: str) -> str:
    """The text between the markers, built from the report and nothing else."""
    summary = _section(report, "## Summary")
    packs = re.findall(r"^## (?!Summary)(\S+)\n", report, re.M)
    if not packs:
        raise ResultsError(f"{REPORT}: no pack section")
    parts = [
        "Results of the evals on each client's golden set, from recorded runs replayed offline "
        "(synthetic data). Generated from [`evals/report.md`](evals/report.md); never typed.",
        summary,
    ]
    for pack in packs:
        body = report.split(f"\n## {pack}\n", 1)[1]
        body = re.split(r"\n## ", body, maxsplit=1)[0]
        parts.append(
            f"**{pack}**, before and after the agent:\n\n"
            + _section(body, "### Before and after the agent")
        )
    if "FAIL" in summary:
        parts.append(
            "A pack ships only when every threshold passes. Packs marked FAIL are below at least "
            "one of theirs, and the report says which."
        )
    else:
        parts.append("Every pack meets its thresholds.")
    return "\n\n".join(parts)


def inject(readme: str, block: str) -> str:
    """The README with the block between its markers replaced."""
    if (
        readme.count(START) != 1
        or readme.count(END) != 1
        or readme.index(START) > readme.index(END)
    ):
        raise ResultsError(f"{README}: needs exactly one {START} followed by one {END}")
    head, rest = readme.split(START, 1)
    tail = rest.split(END, 1)[1]
    return f"{head}{START}\n{block}\n{END}{tail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the block is stale")
    parser.add_argument("--readme", type=Path, default=README)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    try:
        report = args.report.read_text(encoding="utf-8")
        current = args.readme.read_text(encoding="utf-8")
        updated = inject(current, build_block(report))
    except (OSError, ResultsError) as exc:
        print(exc, file=sys.stderr)
        return 1
    if updated == current:
        return 0
    if args.check:
        print(
            f"{args.readme}: the results block is stale: run `make readme-results` "
            "(never edit it by hand)",
            file=sys.stderr,
        )
        return 1
    args.readme.write_text(updated, encoding="utf-8")
    print(f"updated the results block of {args.readme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
