from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from groundwork.core.domain.errors import GroundworkError, NotFoundError, PackError
from groundwork.core.domain.facts import Company, Contact, Deal, Product

PRODUCT: dict[str, Any] = {
    "id": "p_1",
    "name": "Pro plan",
    "description": "Hosted plan",
    "price": "1200.50",
    "currency": "EUR",
    "allowed_claims": ["99.9% uptime SLA"],
}
CONTACT: dict[str, Any] = {
    "id": "c_1",
    "first_name": "Ada",
    "last_name": "Example",
    "email": "ada@example.com",
    "company_id": "co_1",
    "persona": "economic-buyer",
}
DEAL: dict[str, Any] = {
    "id": "d_1",
    "contact_id": "c_1",
    "name": "Pro plan renewal",
    "stage": "negotiation",
    "amount": "2400",
    "product_ids": ["p_1"],
}


def test_money_is_decimal_and_exact() -> None:
    product = Product.model_validate(PRODUCT)
    assert product.price == Decimal("1200.50")
    assert isinstance(product.price, Decimal)
    assert product.allowed_claims == ("99.9% uptime SLA",)


def test_facts_are_frozen() -> None:
    product = Product.model_validate(PRODUCT)
    with pytest.raises(ValidationError):
        product.price = Decimal(0)  # type: ignore[misc]


@pytest.mark.parametrize("model, data", [(Product, PRODUCT), (Contact, CONTACT), (Deal, DEAL)])
def test_unknown_field_is_rejected(
    model: type[Product | Contact | Deal], data: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**data, "hubspot_owner_id": "42"})


@pytest.mark.parametrize(
    "model, data, field, value",
    [
        (Product, PRODUCT, "price", "-1"),
        (Product, PRODUCT, "currency", "euro"),
        (Product, PRODUCT, "id", ""),
        (Contact, CONTACT, "email", "not-an-email"),
        (Deal, DEAL, "amount", "abc"),
    ],
)
def test_invalid_values_are_rejected(
    model: type[Product | Contact | Deal], data: dict[str, Any], field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**data, field: value})


def test_contact_notes_default_to_empty() -> None:
    assert Contact.model_validate(CONTACT).notes == ""


def test_company_requires_a_name() -> None:
    with pytest.raises(ValidationError):
        Company(id="co_1", name="", segment="smb", country="FR")


def test_not_found_error_names_kind_and_id() -> None:
    error = NotFoundError("contact", "c_99")
    assert (error.kind, error.id) == ("contact", "c_99")
    assert str(error) == "contact 'c_99' not found"
    assert isinstance(error, GroundworkError)


def test_pack_error_keeps_message() -> None:
    error = PackError("client_packs/acme: bad config")
    assert error.message == str(error) == "client_packs/acme: bad config"
