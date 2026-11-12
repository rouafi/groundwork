"""Check the claims of a text against the CRM: judgment by the model, verdict by code.

Step 1, the cheap model lists the atomic claims of the text (the text travels as a
document: untrusted data). Step 2 is deterministic and decides the status:
- price: the amount and currency must equal the product's price, else `false`;
  a price that cannot be read fully, or for no known product, is `unknown`.
- product_name: the name must be in the catalog, else `false` (fabricated product).
- feature: an `allowed_claims` entry of the product (or of any product when none is
  named) must appear in the claim, else `unknown`. Word containment, like the
  extraction workflow (ADR 0007): a paraphrase of an allowed claim stays `unknown`.
- other: `unknown`.

The model only finds claims; it never decides whether one is true.
"""

import re
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict

from groundwork.core.domain.claims import ClaimCheck, ExtractedClaim
from groundwork.core.domain.facts import Product
from groundwork.core.ports.crm import CrmPort
from groundwork.core.ports.model import ModelPort
from groundwork.core.services.rules_check import matching_allowed_claim

CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}
CURRENCY_CODES = frozenset({"EUR", "USD", "GBP", "CHF", "CAD", "AUD", "JPY"})
_NUMBER = re.compile(r"\d(?:[\d\s.,]*\d)?")
_CODE = re.compile(r"\b[A-Za-z]{3}\b")


class ExtractedClaims(BaseModel):
    """The structured answer of the extraction step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claims: tuple[ExtractedClaim, ...]


def check_claims(text: str, crm: CrmPort, model: ModelPort, system: str) -> tuple[ClaimCheck, ...]:
    """Every claim of `text`, in order, with its status and the fact it was checked against."""
    catalog = crm.get_products(crm.list_product_ids())
    answer = model.complete_structured(
        tier="cheap",
        system=system,
        user=_request(catalog),
        schema=ExtractedClaims,
        document=text,
    )
    return tuple(verify(claim, catalog) for claim in answer.value.claims)


def verify(claim: ExtractedClaim, catalog: Sequence[Product]) -> ClaimCheck:
    """The deterministic verdict on one extracted claim."""
    by_id = {p.id: p for p in catalog}
    if claim.kind == "price":
        return _price(claim, by_id.get(claim.product_id or ""))
    if claim.kind == "product_name":
        return _product_name(claim, catalog)
    if claim.kind == "feature":
        product = by_id.get(claim.product_id or "")
        return _feature(claim, (product,) if product else catalog)
    return _check(claim, "unknown", "no fact to check this kind of claim against")


def parse_price(value: str) -> tuple[Decimal | None, str | None]:
    """Amount and ISO currency of a written price; None for what cannot be read.

    '1,490 EUR', '1 490,00 €' and '€1.490' all read as 1490 EUR. A separator
    followed by exactly three digits, alone of its kind, groups thousands.
    """
    number = _NUMBER.search(value)
    amount = _amount(number.group()) if number else None
    symbol = next((code for sym, code in CURRENCY_SYMBOLS.items() if sym in value), None)
    codes = (m.group().upper() for m in _CODE.finditer(value))
    currency = symbol or next((c for c in codes if c in CURRENCY_CODES), None)
    return amount, currency


def _amount(written: str) -> Decimal | None:
    digits = re.sub(r"\s", "", written)
    separators = [c for c in digits if c in ".,"]
    if separators:
        last = separators[-1]
        decimals = digits.rsplit(last, 1)[1]
        is_decimal = len(set(separators)) == 2 or (
            separators.count(last) == 1 and len(decimals) != 3
        )
        whole = digits.rsplit(last, 1)[0] if is_decimal else digits
        whole = re.sub(r"[.,]", "", whole)
        digits = f"{whole}.{decimals}" if is_decimal else whole
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def _price(claim: ExtractedClaim, product: Product | None) -> ClaimCheck:
    if product is None:
        reason = f"no catalog product for this price: {claim.product_id}"
        return _check(claim, "unknown", reason)
    amount, currency = parse_price(claim.value or "")
    catalog_price = f"{product.id} costs {product.price} {product.currency}"
    if amount is None:
        return _check(claim, "unknown", f"no amount could be read; {catalog_price}")
    if amount != product.price or (currency is not None and currency != product.currency):
        return _check(claim, "false", catalog_price, product.id)
    if currency is None:
        return _check(claim, "unknown", f"no currency stated; {catalog_price}")
    return _check(claim, "verified", catalog_price, product.id)


def _product_name(claim: ExtractedClaim, catalog: Sequence[Product]) -> ClaimCheck:
    name = claim.value or claim.text
    product = next((p for p in catalog if _words(p.name) == _words(name)), None)
    if product is None:
        return _check(claim, "false", f"no product named {name!r} in the catalog")
    return _check(claim, "verified", f"{product.id} is {product.name}", product.id)


def _feature(claim: ExtractedClaim, products: Sequence[Product]) -> ClaimCheck:
    for product in products:
        allowed = matching_allowed_claim(claim.text, product.allowed_claims)
        if allowed is not None:
            return _check(claim, "verified", f"{product.id} allows {allowed!r}", product.id)
    names = ", ".join(p.id for p in products) or "the catalog"
    return _check(claim, "unknown", f"not in the allowed claims of {names}; a human decides")


def _check(
    claim: ExtractedClaim, status: str, reason: str, evidence: str | None = None
) -> ClaimCheck:
    return ClaimCheck.model_validate(
        {
            "claim": claim.text,
            "kind": claim.kind,
            "status": status,
            "evidence": evidence,
            "reason": reason,
        }
    )


def _words(text: str) -> str:
    return " ".join(text.casefold().split())


def _request(catalog: Sequence[Product]) -> str:
    listed = "\n".join(f"- {p.id}: {p.name}" for p in catalog)
    return f"Product catalog:\n{listed}\n\nList every claim the document makes."
