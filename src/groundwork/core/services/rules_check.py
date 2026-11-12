"""Check know-how against facts: a claim rule may only allow what the CRM allows.

The bridge between the two ontologies, made verifiable. An expert saying "Pro
includes SSO" while the CRM does not list it in the product's `allowed_claims` is a
contradiction between what people say and what the system of record says. It is
reported before review and blocks `validate-packs` once such a rule is approved.
"""

from collections.abc import Mapping, Sequence

from groundwork.core.domain.domain_pack import DomainPack
from groundwork.core.domain.errors import NotFoundError
from groundwork.core.domain.knowhow import ClaimContradiction, Interview, Rule
from groundwork.core.ports.crm import CrmPort
from groundwork.core.services.grounding import normalize


def rule_problems(
    rules: Sequence[Rule],
    interviews: Mapping[str, Interview],
    domain: DomainPack,
    crm: CrmPort,
) -> list[str]:
    """Every problem in a pack's `rules.yaml`, one line each, starting with the rule id.

    All rules: unique ids, scope in the vocabulary, known products. Approved rules
    also: every provenance quote is the exact span of an existing interview, and a
    claim never allows what the CRM does not.
    """
    ids = [r.id for r in rules]
    problems = [
        f"rule {i} is defined more than once" for i in sorted({i for i in ids if ids.count(i) > 1})
    ]
    product_ids = set(crm.list_product_ids())
    for rule in rules:
        problems += _scope_problems(rule, domain)
        problems += [
            f"rule {rule.id} references missing product {p}"
            for p in rule.product_ids
            if p not in product_ids
        ]
        if rule.status == "approved":
            problems += _provenance_problems(rule, interviews)
    approved = [r for r in rules if r.status == "approved"]
    problems += [
        f"rule {c.rule_id} claims {c.claim_text!r} for {c.product_id}, not in its allowed_claims"
        for c in claim_contradictions(approved, crm)
    ]
    return problems


def _scope_problems(rule: Rule, domain: DomainPack) -> list[str]:
    scope = rule.scope
    problems = []
    if scope.channel != "any" and scope.channel not in domain.channels:
        problems.append(
            f"rule {rule.id} has channel {scope.channel!r}, not in the domain vocabulary"
        )
    problems += [
        f"rule {rule.id} has segment {s!r}, not in the domain vocabulary"
        for s in scope.segments
        if s not in domain.segments
    ]
    problems += [
        f"rule {rule.id} has persona {p!r}, not in the domain vocabulary"
        for p in scope.personas
        if p not in domain.personas
    ]
    return problems


def _provenance_problems(rule: Rule, interviews: Mapping[str, Interview]) -> list[str]:
    problems = []
    for p in rule.provenance:
        interview = interviews.get(p.interview_id)
        if interview is None:
            problems.append(f"rule {rule.id} cites missing interview {p.interview_id}")
        elif interview.text[p.start : p.end] != p.quote:
            problems.append(
                f"rule {rule.id} cites a quote absent from {p.interview_id} "
                f"at {p.start}-{p.end}: {p.quote!r}"
            )
    return problems


def claim_contradictions(rules: Sequence[Rule], crm: CrmPort) -> tuple[ClaimContradiction, ...]:
    """Every (rule, product) pair where the rule's claim_text is not an allowed claim."""
    found = []
    for rule in rules:
        if rule.claim_text is None:
            continue
        for product_id in rule.product_ids:
            if not _allowed(rule.claim_text, product_id, crm):
                found.append(
                    ClaimContradiction(
                        rule_id=rule.id, product_id=product_id, claim_text=rule.claim_text
                    )
                )
    return tuple(found)


def _allowed(claim_text: str, product_id: str, crm: CrmPort) -> bool:
    try:
        (product,) = crm.get_products([product_id])
    except NotFoundError:
        return False
    wanted = _key(claim_text)
    return any(_key(allowed) == wanted for allowed in product.allowed_claims)


def _key(text: str) -> str:
    return normalize(text).casefold().rstrip(".")
