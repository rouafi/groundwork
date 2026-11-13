"""Stage-based validation of a client pack: what each day of the playbook must have produced.

`stage_problems(pack_dir, "day3", ...)` checks days 1, 2 and 3: a pack on day 3 still needs
its signed-off discovery. Every problem starts with its day, then the file and the field, so
a person knows what to fill. Nothing here signs, approves or ticks anything: those are human
actions, and this module only reports whether they were recorded.
"""

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from groundwork.core.domain.discovery import DiscoveryDoc
from groundwork.core.domain.errors import PackError
from groundwork.core.services.integrity import check_integrity
from groundwork.core.services.packs import (
    load_domain_pack,
    load_interviews,
    load_pack_config,
    load_rules,
)
from groundwork.core.services.rules_check import rule_problems
from groundwork.entrypoints.wiring import build_crm

DISCOVERY_FILE = "discovery.yaml"
MIN_INTERVIEWS = 3


class Stage(StrEnum):
    day1 = "day1"
    day2 = "day2"
    day3 = "day3"


def stage_problems(pack_dir: Path, stage: Stage, domains_dir: Path) -> list[str]:
    """Every problem of days 1 to `stage`, each prefixed by its day."""
    problems: list[str] = []
    for day in Stage:
        problems += [f"{day.value}: {p}" for p in _CHECKS[day](pack_dir, domains_dir)]
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


def _field(error: Any) -> str:
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else str(error["msg"])


_CHECKS = {Stage.day1: _day1, Stage.day2: _day2, Stage.day3: _day3}
