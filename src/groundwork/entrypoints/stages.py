"""Stage-based validation of a client pack: what each day of the playbook must have produced.

`stage_problems(pack_dir, "day3", ...)` checks days 1, 2 and 3: a pack on day 3 still needs
its signed-off discovery. Every problem starts with its day, then the file and the field, so
a person knows what to fill. Nothing here signs, approves or ticks anything: those are human
actions, and this module only reports whether they were recorded.

Day 5 runs the evals on replay, whatever the environment says, and holds the pack to its own
thresholds: it never accepts a pack below them.
"""

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from groundwork.core.domain.discovery import DiscoveryDoc
from groundwork.core.domain.errors import GroundworkError, PackError
from groundwork.core.services.evals.runner import run_pack
from groundwork.core.services.integrity import check_integrity
from groundwork.core.services.packs import (
    CALIBRATION_FILE,
    GOLDEN_FILE,
    POLICIES_FILE,
    RUBRIC_FILE,
    THRESHOLDS_FILE,
    load_calibration,
    load_domain_pack,
    load_golden,
    load_interviews,
    load_pack_config,
    load_pack_policies,
    load_rubric,
    load_rules,
    load_thresholds,
)
from groundwork.core.services.rules_check import rule_problems
from groundwork.entrypoints.evals_cli import build_eval_deps
from groundwork.entrypoints.wiring import EMBEDDING_ENV, MODEL_ENV, RECORD_ENV, build_crm

DISCOVERY_FILE = "discovery.yaml"
GO_LIVE_FILE = "go_live.md"
CHECKLIST_TEMPLATE = "go-live-checklist.md"
MIN_INTERVIEWS = 3
MIN_GOLDEN_CASES = 20
CHECKBOX = re.compile(r"^\s*[-*] \[(?P<mark>[ xX])\]\s*(?P<text>.*)$")


class Stage(StrEnum):
    day1 = "day1"
    day2 = "day2"
    day3 = "day3"
    day4 = "day4"
    day5 = "day5"


def stage_problems(
    pack_dir: Path,
    stage: Stage,
    domains_dir: Path,
    traces_dir: Path = Path("traces"),
    playbook_dir: Path = Path("playbook"),
) -> list[str]:
    """Every problem of days 1 to `stage`, each prefixed by its day.

    Day 5 runs the evals only when days 1 to 4 are clean: a broken pack cannot be measured.
    """
    problems: list[str] = []
    for day in Stage:
        if day is Stage.day5:
            found = _day5(pack_dir, domains_dir, traces_dir, playbook_dir, measurable=not problems)
        else:
            found = _CHECKS[day](pack_dir, domains_dir)
        problems += [f"{day.value}: {p}" for p in found]
        if day == stage:
            break
    return problems


def _day1(pack_dir: Path, domains_dir: Path) -> list[str]:
    path = pack_dir / DISCOVERY_FILE
    if not path.is_file():
        return [f"{DISCOVERY_FILE} not found (groundwork new-pack creates it)"]
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"{DISCOVERY_FILE}: not valid YAML ({exc})"]
    try:
        doc = DiscoveryDoc.model_validate(data)
    except ValidationError as exc:
        return [f"{DISCOVERY_FILE}: {_field(e)}" for e in exc.errors()]
    problems = []
    if doc.client != pack_dir.name:
        problems.append(
            f"{DISCOVERY_FILE}: client {doc.client!r} is not the pack's name {pack_dir.name!r}"
        )
    if not doc.is_signed_off:
        problems.append(
            f"{DISCOVERY_FILE}: status is draft: the sponsor signs it off, and a person records "
            "it with status: signed_off and signed_off_by"
        )
    return problems


def _day2(pack_dir: Path, domains_dir: Path) -> list[str]:
    try:
        config = load_pack_config(pack_dir)
        domain = load_domain_pack(domains_dir, config.domain)
        crm = build_crm(pack_dir, config)
        problems = [str(issue) for issue in check_integrity(crm, domain)]
        counts = {
            "contacts": len(crm.list_contact_ids()),
            "companies": len(crm.list_company_ids()),
            "products": len(crm.list_product_ids()),
        }
    except PackError as exc:
        return [exc.message]
    return problems + [f"fixtures: no {kind}" for kind, n in counts.items() if n == 0]


def _day3(pack_dir: Path, domains_dir: Path) -> list[str]:
    try:
        config = load_pack_config(pack_dir)
        domain = load_domain_pack(domains_dir, config.domain)
        crm = build_crm(pack_dir, config)
        interviews = load_interviews(pack_dir)
        rules = load_rules(pack_dir)
    except PackError as exc:
        return [exc.message]
    problems = []
    if len(interviews) < MIN_INTERVIEWS:
        problems.append(f"interviews: {len(interviews)} found, at least {MIN_INTERVIEWS} needed")
    if not any(r.status == "approved" for r in rules):
        problems.append(
            "rules.yaml: no approved rule: a person reviews the proposals of "
            "extract-rules and sets status: approved"
        )
    by_id = {i.id: i for i in interviews}
    return problems + rule_problems(rules, by_id, domain, crm)


def _day4(pack_dir: Path, domains_dir: Path) -> list[str]:
    try:
        config = load_pack_config(pack_dir)
        crm = build_crm(pack_dir, config)
        cases = load_golden(pack_dir)
        thresholds = load_thresholds(pack_dir)
        calibration = load_calibration(pack_dir)
        rubric = load_rubric(pack_dir)
    except PackError as exc:
        return [exc.message]
    problems = []
    if len(cases) < MIN_GOLDEN_CASES:
        problems.append(
            f"{GOLDEN_FILE}: {len(cases)} case(s) found, at least {MIN_GOLDEN_CASES} needed"
        )
    contacts = set(crm.list_contact_ids())
    problems += [
        f"{GOLDEN_FILE}: case {c.id} uses contact {c.contact_id}, which is not in the fixtures"
        for c in cases
        if c.contact_id not in contacts
    ]
    if thresholds is None:
        problems.append(f"{THRESHOLDS_FILE} not found: agree the thresholds with the sponsor")
    if rubric is None:
        problems.append(f"{RUBRIC_FILE} not found: the judge scores tone against it")
    if not calibration:
        problems.append(
            f"{CALIBRATION_FILE}: no email scored by a person: the judge cannot be calibrated"
        )
    return problems


def _day5(
    pack_dir: Path, domains_dir: Path, traces_dir: Path, playbook_dir: Path, measurable: bool
) -> list[str]:
    problems: list[str] = []
    try:
        if not (pack_dir / POLICIES_FILE).is_file():
            problems.append(f"{POLICIES_FILE} not found: write the pack's policies, even if empty")
        else:
            load_pack_policies(pack_dir)
    except PackError as exc:
        problems.append(exc.message)
    problems += _checklist_problems(pack_dir / GO_LIVE_FILE, playbook_dir / CHECKLIST_TEMPLATE)
    if not measurable:
        return [*problems, "evals: not run: fix days 1 to 4 first"]
    return problems + _eval_problems(pack_dir, domains_dir, traces_dir)


def _checklist_problems(path: Path, template: Path) -> list[str]:
    """Every box of the playbook's checklist must be in `go_live.md` and ticked.

    A box deleted from the pack's copy counts as a box not ticked: the gate cannot be
    passed by shortening the list. Boxes a client adds are held to the same rule.
    """
    if not path.is_file():
        return [f"{GO_LIVE_FILE} not found (groundwork new-pack creates it)"]
    if not template.is_file():
        return [f"{template}: playbook checklist not found: run from the repository root"]
    expected = [text for _, text in _boxes(template)]
    found = _boxes(path)
    if not found:
        return [f"{GO_LIVE_FILE}: no checklist box: copy {template}"]
    ticked = {text for mark, text in found if mark != " "}
    present = {text for _, text in found}
    problems = [
        f"{GO_LIVE_FILE}: box missing: {text} (copy it back from {template})"
        for text in expected
        if text not in present
    ]
    problems += [
        f"{GO_LIVE_FILE}: not ticked: {text} (a person ticks it after checking the point)"
        for _, text in found
        if text not in ticked
    ]
    return problems


def _boxes(path: Path) -> list[tuple[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [(m["mark"], m["text"].strip()) for line in lines if (m := CHECKBOX.match(line))]


def _eval_problems(pack_dir: Path, domains_dir: Path, traces_dir: Path) -> list[str]:
    """Run the pack's evals on replay and name every threshold it misses."""
    try:
        with _replay_only():
            result = run_pack(build_eval_deps(pack_dir, domains_dir, traces_dir))
    except GroundworkError as exc:
        return [f"evals: {exc}"]
    return [f"evals: {t.message}" for t in result.thresholds if not t.passed]


@contextmanager
def _replay_only() -> Iterator[None]:
    """Replay with no recording, whatever the shell says: a stage check never costs money."""
    keep = {k: os.environ.get(k) for k in (MODEL_ENV, EMBEDDING_ENV, RECORD_ENV)}
    os.environ[MODEL_ENV] = os.environ[EMBEDDING_ENV] = "replay"
    os.environ.pop(RECORD_ENV, None)
    try:
        yield
    finally:
        for key, value in keep.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _field(error: Any) -> str:
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else str(error["msg"])


_CHECKS = {Stage.day1: _day1, Stage.day2: _day2, Stage.day3: _day3, Stage.day4: _day4}
