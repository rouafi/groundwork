from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from groundwork.core.domain.errors import PackError
from groundwork.core.domain.facts import Product
from groundwork.core.domain.knowhow import Interview, Provenance, Rule, Scope
from groundwork.core.services.packs import load_rules
from groundwork.core.services.rules_check import rule_problems
from tests.fakes import InMemoryCrm
from tests.unit.test_grounding import DOMAIN

TEXT = "Never discount in writing. Keep it short."
INTERVIEWS = {"acme-i-1": Interview(id="acme-i-1", role="sales", text=TEXT)}
CRM = InMemoryCrm(
    products=[
        Product(
            id="acme-p-1",
            name="Pro",
            description="",
            price=Decimal(1),
            currency="EUR",
            allowed_claims=("Setup in one day",),
        )
    ]
)


def _rule(**fields: Any) -> Rule:
    provenance = Provenance(interview_id="acme-i-1", quote="Keep it short.", start=27, end=41)
    defaults: dict[str, Any] = {
        "id": "acme-r-001",
        "kind": "tone",
        "statement": "Be short.",
        "provenance": (provenance,),
        "status": "approved",
    }
    return Rule(**(defaults | fields))


def _problems(*rules: Rule) -> list[str]:
    return rule_problems(rules, INTERVIEWS, DOMAIN, CRM)


def test_a_valid_approved_rule_has_no_problem() -> None:
    claim = _rule(
        id="acme-r-002", kind="claim", product_ids=("acme-p-1",), claim_text="setup in one day"
    )
    assert _problems(_rule(), claim) == []


def test_every_rule_is_checked_for_ids_scope_and_products() -> None:
    bad_scope = Scope(segments=("startup",), personas=("ceo",))
    problems = _problems(
        _rule(),
        _rule(scope=bad_scope, status="proposed"),
        _rule(id="acme-r-003", product_ids=("acme-p-9",), status="proposed"),
    )
    assert problems == [
        "rule acme-r-001 is defined more than once",
        "rule acme-r-001 has segment 'startup', not in the domain vocabulary",
        "rule acme-r-001 has persona 'ceo', not in the domain vocabulary",
        "rule acme-r-003 references missing product acme-p-9",
    ]


def test_channel_outside_the_domain_is_reported() -> None:
    narrow = DOMAIN.model_copy(update={"channels": ("external",)})
    problems = rule_problems([_rule(scope=Scope(channel="internal"))], INTERVIEWS, narrow, CRM)
    assert problems == ["rule acme-r-001 has channel 'internal', not in the domain vocabulary"]


def test_only_approved_rules_must_be_grounded() -> None:
    elsewhere = Provenance(interview_id="acme-i-9", quote="x", start=0, end=1)
    moved = Provenance(interview_id="acme-i-1", quote="Keep it short.", start=0, end=14)
    assert _problems(_rule(provenance=(elsewhere,), status="proposed")) == []
    assert _problems(_rule(provenance=(elsewhere, moved))) == [
        "rule acme-r-001 cites missing interview acme-i-9",
        "rule acme-r-001 cites a quote absent from acme-i-1 at 0-14: 'Keep it short.'",
    ]


def test_rules_file_loads_or_is_absent(tmp_path: Path) -> None:
    assert load_rules(tmp_path) == ()
    (tmp_path / "rules.yaml").write_text(_rule().model_dump_json())
    with pytest.raises(PackError, match=r"rules\.yaml"):
        load_rules(tmp_path)
    (tmp_path / "rules.yaml").write_text(f"[{_rule().model_dump_json()}]")
    assert load_rules(tmp_path) == (_rule(),)
