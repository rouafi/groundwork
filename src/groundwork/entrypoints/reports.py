"""Write an extraction run to disk and summarize it for the FDE who reviews it."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from groundwork.core.domain.knowhow import ExtractionReport
from groundwork.core.services.golden_checks import GoldenCheck

PROPOSED_FILE = "rules.proposed.yaml"
REPORT_FILE = "extraction_report.yaml"


def write_run(report: ExtractionReport, out_dir: Path) -> tuple[Path, Path]:
    """Write the proposed rules and the full report as stable, diff-friendly YAML."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rules = [r.model_dump(mode="json", exclude_none=True) for r in report.rules]
    review = report.model_dump(mode="json", exclude_none=True, exclude={"rules"})
    proposed, full = out_dir / PROPOSED_FILE, out_dir / REPORT_FILE
    proposed.write_text(_yaml(rules), encoding="utf-8")
    full.write_text(_yaml(review), encoding="utf-8")
    return proposed, full


def summary(report: ExtractionReport, checks: Sequence[GoldenCheck]) -> list[str]:
    """What a reviewer needs first: counts, reasons, disagreements, gaps, cost, failures."""
    lines = [f"{report.pack}: {len(report.rules)} rule(s) proposed, {len(report.dropped)} dropped"]
    lines += [f"  dropped ({d.interview_id}): {d.reason}: {d.statement}" for d in report.dropped]
    lines += [f"  conflict {' vs '.join(c.rule_ids)}: {c.reason}" for c in report.conflicts]
    lines += [
        f"  contradiction {c.rule_id}: claims {c.claim_text!r} for {c.product_id}, "
        "not in its allowed_claims"
        for c in report.contradictions
    ]
    lines += [f"  gap {g.segment} / {g.persona}: {g.contacts} contact(s)" for g in report.gaps]
    lines += [f"  ask next: {q}" for q in report.questions]
    lines += [
        f"  cost {u.stage}: {u.calls} call(s), {u.usage.input_tokens} in, "
        f"{u.usage.output_tokens} out"
        for u in report.usage
    ]
    lines += [f"  golden {check}" for check in checks]
    lines += [f"  FAILED {f.where}: {f.error}" for f in report.failures]
    return lines


def _yaml(data: Any) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
