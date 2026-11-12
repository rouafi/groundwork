"""Check CRM facts against themselves and against the domain vocabulary.

Works through `CrmPort` only, so the same check runs on fixtures in CI and,
later, on a live CRM from a manual command.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from groundwork.core.domain.domain_pack import DomainPack
from groundwork.core.domain.evals import GoldenCase
from groundwork.core.domain.harmonize import DemoCase
from groundwork.core.ports.crm import CrmPort


@dataclass(frozen=True)
class IntegrityIssue:
    """One problem, located by object kind and id."""

    kind: str
    id: str
    problem: str

    def __str__(self) -> str:
        return f"{self.kind} {self.id} {self.problem}"


def check_integrity(crm: CrmPort, domain: DomainPack) -> tuple[IntegrityIssue, ...]:
    """Return every dangling reference and every value outside the domain vocabulary."""
    company_ids = set(crm.list_company_ids())
    contact_ids = set(crm.list_contact_ids())
    product_ids = set(crm.list_product_ids())
    return (
        *_check_companies(crm, domain),
        *_check_contacts(crm, domain, company_ids),
        *_check_deals(crm, contact_ids, product_ids),
    )


def _check_companies(crm: CrmPort, domain: DomainPack) -> list[IntegrityIssue]:
    issues = []
    for company_id in crm.list_company_ids():
        segment = crm.get_company(company_id).segment
        if segment not in domain.segments:
            issues.append(_outside("company", company_id, "segment", segment, domain.segments))
    return issues


def _check_contacts(
    crm: CrmPort, domain: DomainPack, company_ids: set[str]
) -> list[IntegrityIssue]:
    issues = []
    for contact_id in crm.list_contact_ids():
        contact = crm.get_contact(contact_id)
        if contact.company_id not in company_ids:
            issues.append(_missing("contact", contact_id, "company", contact.company_id))
        if contact.persona not in domain.personas:
            persona = contact.persona
            issues.append(_outside("contact", contact_id, "persona", persona, domain.personas))
    return issues


def _check_deals(
    crm: CrmPort, contact_ids: set[str], product_ids: set[str]
) -> list[IntegrityIssue]:
    issues = []
    for deal_id in crm.list_deal_ids():
        deal = crm.get_deal(deal_id)
        if deal.contact_id not in contact_ids:
            issues.append(_missing("deal", deal_id, "contact", deal.contact_id))
        issues.extend(
            _missing("deal", deal_id, "product", product_id)
            for product_id in deal.product_ids
            if product_id not in product_ids
        )
    return issues


def _missing(kind: str, id: str, target: str, target_id: str) -> IntegrityIssue:
    return IntegrityIssue(kind, id, f"references missing {target} {target_id}")


def _outside(
    kind: str, id: str, field: str, value: str, allowed: tuple[str, ...]
) -> IntegrityIssue:
    problem = f"has {field} {value!r}, not in the domain vocabulary ({', '.join(allowed)})"
    return IntegrityIssue(kind, id, problem)


def golden_case_problems(
    cases: Sequence[GoldenCase], crm: CrmPort, has_thresholds: bool, has_rubric: bool
) -> list[str]:
    """Every golden case whose contact is unknown, and what a pack with a golden set lacks."""
    known = set(crm.list_contact_ids())
    problems = [
        f"golden case {case.id}: unknown contact {case.contact_id!r}"
        for case in cases
        if case.contact_id not in known
    ]
    if cases and not has_thresholds:
        problems.append("golden.jsonl has cases but thresholds.yaml is missing")
    if cases and not has_rubric:
        problems.append("golden.jsonl has cases but rubric.md is missing")
    return problems


def demo_problems(cases: Sequence[DemoCase], crm: CrmPort) -> list[str]:
    """Every demo case whose contact is not in the CRM, by case id."""
    known = set(crm.list_contact_ids())
    return [
        f"demo case {case.case_id}: unknown contact {case.contact_id!r}"
        for case in cases
        if case.contact_id not in known
    ]
