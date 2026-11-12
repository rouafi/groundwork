"""Check know-how against facts: a claim rule may only allow what the CRM allows.

The bridge between the two ontologies, made verifiable. An expert saying "Pro
includes SSO" while the CRM does not list it in the product's `allowed_claims` is a
contradiction between what people say and what the system of record says. It is
reported before review and blocks `validate-packs` once such a rule is approved.
"""

from collections.abc import Sequence

from groundwork.core.domain.errors import NotFoundError
from groundwork.core.domain.knowhow import ClaimContradiction, Rule
from groundwork.core.ports.crm import CrmPort
from groundwork.core.services.grounding import normalize


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
