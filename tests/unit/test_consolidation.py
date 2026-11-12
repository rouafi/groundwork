from decimal import Decimal
from typing import Any

from groundwork.core.domain.facts import Company, Contact, Product
from groundwork.core.domain.knowhow import Provenance, Rule, Scope
from groundwork.core.services.consolidation import (
    MAX_QUESTIONS,
    consolidate,
    coverage_gaps,
    follow_up_questions,
)
from groundwork.core.services.rules_check import claim_contradictions
from tests.fakes import InMemoryCrm, StubModel
from tests.unit.test_grounding import DOMAIN


def _rule(n: int, interview: str = "acme-i-1", **fields: Any) -> Rule:
    provenance = Provenance(interview_id=interview, quote=f"q{n}", start=n, end=n + 2)
    return Rule(
        id=f"acme-r-{n:03d}",
        kind=fields.pop("kind", "practice"),
        statement=f"Rule {n}.",
        provenance=(provenance,),
        **fields,
    )


RULES = [_rule(1), _rule(2), _rule(3, "acme-i-2"), _rule(4, "acme-i-2")]


def _consolidate(answer: dict[str, Any], rules: list[Rule] = RULES) -> Any:
    model = StubModel(structured=lambda **_: answer)
    return consolidate("acme", rules, model, "system"), model


def test_duplicates_are_merged_keeping_every_provenance_and_ids_renumbered() -> None:
    result, _ = _consolidate(
        {
            "duplicates": [{"rule_ids": ["acme-r-003", "acme-r-001"], "reason": "same"}],
            "conflicts": [],
        }
    )
    assert [r.id for r in result.rules] == ["acme-r-001", "acme-r-002", "acme-r-003"]
    first = result.rules[0]
    assert [p.quote for p in first.provenance] == ["q1", "q3"]
    assert result.rules[2].statement == "Rule 4."
    assert result.usage.stage == "consolidate"


def test_conflicts_are_flagged_with_renumbered_ids_and_rules_kept() -> None:
    result, _ = _consolidate(
        {
            "duplicates": [{"rule_ids": ["acme-r-001", "acme-r-002"], "reason": "same"}],
            "conflicts": [{"rule_ids": ["acme-r-002", "acme-r-004"], "reason": "discounts"}],
        }
    )
    assert len(result.rules) == 3
    (conflict,) = result.conflicts
    assert conflict.rule_ids == ("acme-r-001", "acme-r-003")
    assert conflict.reason == "discounts"


def test_references_to_unknown_or_single_rules_are_ignored() -> None:
    result, _ = _consolidate(
        {
            "duplicates": [
                {"rule_ids": ["acme-r-001", "acme-r-999"], "reason": "x"},
                {"rule_ids": ["acme-r-002", "acme-r-003"], "reason": "y"},
                {"rule_ids": ["acme-r-003", "acme-r-004"], "reason": "already used"},
            ],
            "conflicts": [{"rule_ids": ["acme-r-001", "acme-r-001"], "reason": "self"}],
        }
    )
    assert [len(r.provenance) for r in result.rules] == [1, 2, 1]
    assert result.conflicts == ()


def test_fewer_than_two_rules_skip_the_model() -> None:
    result, model = _consolidate({}, rules=[_rule(1)])
    assert result.rules == (_rule(1),) and result.usage is None and model.calls == []


def _crm() -> InMemoryCrm:
    return InMemoryCrm(
        companies=[
            Company(id="co-1", name="A", segment="smb", country="FR"),
            Company(id="co-2", name="B", segment="mid-market", country="FR"),
        ],
        contacts=[
            Contact(
                id=f"c-{n}",
                first_name="x",
                last_name="y",
                email=f"c{n}@example.com",
                company_id=company,
                persona=persona,
            )
            for n, (company, persona) in enumerate(
                [("co-1", "end-user"), ("co-1", "end-user"), ("co-2", "economic-buyer")]
            )
        ],
        products=[
            Product(
                id="acme-p-1",
                name="Pro",
                description="",
                price=Decimal(1),
                currency="EUR",
                allowed_claims=("Single sign-on included",),
            ),
        ],
    )


def test_gaps_are_audiences_with_contacts_and_no_specific_rule() -> None:
    general = _rule(1)
    gaps = coverage_gaps([general], DOMAIN, _crm())
    assert [(g.segment, g.persona, g.contacts) for g in gaps] == [
        ("smb", "end-user", 2),
        ("mid-market", "economic-buyer", 1),
    ]
    specific = _rule(2, scope=Scope(segments=("smb",)))
    assert [(g.segment, g.persona) for g in coverage_gaps([general, specific], DOMAIN, _crm())] == [
        ("mid-market", "economic-buyer")
    ]


def test_questions_target_the_largest_gaps_and_are_capped() -> None:
    gaps = coverage_gaps([], DOMAIN, _crm())
    model = StubModel(structured=lambda **_: {"questions": [f"Q{n}?" for n in range(9)] + [" "]})
    questions, usage = follow_up_questions(gaps, model, "system")
    assert len(questions) == MAX_QUESTIONS and usage is not None
    assert "smb / end-user: 2 contact(s)" in model.calls[0][1]["user"]
    assert follow_up_questions((), model, "system") == ((), None)


def test_claims_outside_allowed_claims_are_contradictions() -> None:
    allowed = _rule(
        1, kind="claim", product_ids=("acme-p-1",), claim_text="single sign-on included."
    )
    invented = _rule(2, kind="claim", product_ids=("acme-p-1",), claim_text="24/7 phone support")
    unknown = _rule(3, kind="claim", product_ids=("acme-p-9",), claim_text="anything")
    prohibition = _rule(4, kind="claim", product_ids=("acme-p-1",))
    found = claim_contradictions([allowed, invented, unknown, prohibition], _crm())
    assert [(c.rule_id, c.product_id) for c in found] == [
        ("acme-r-002", "acme-p-1"),
        ("acme-r-003", "acme-p-9"),
    ]
