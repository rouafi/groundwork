from decimal import Decimal
from typing import Any

import pytest

from groundwork.core.domain.facts import Product
from groundwork.core.services.claims import check_claims, parse_price
from tests.fakes import InMemoryCrm, StubModel

CRM = InMemoryCrm(
    products=[
        Product(
            id="acme-p-2", name="Insight Pro", description="d", price=Decimal("1490.00"),
            currency="EUR", allowed_claims=("Setup in one day", "Full API access"),
        ),
        Product(
            id="acme-p-3", name="Insight Enterprise", description="d", price=Decimal(4900),
            currency="EUR", allowed_claims=("Single sign-on",),
        ),
    ]
)  # fmt: skip

DRAFT = "Insight Pro costs 1,490 EUR."


def _check(*claims: dict[str, Any]) -> tuple[Any, StubModel]:
    model = StubModel(structured=lambda **_: {"claims": list(claims)})
    return check_claims(DRAFT, CRM, model, "system"), model


def _one(**claim: Any) -> Any:
    (result,), _ = _check(claim)
    return result


def test_the_text_goes_to_the_cheap_model_as_a_document_with_the_catalog() -> None:
    _, model = _check()
    ((method, call),) = model.calls
    assert method == "complete_structured"
    assert call["tier"] == "cheap"
    assert call["document"] == DRAFT
    assert "acme-p-2: Insight Pro" in call["user"]
    assert DRAFT not in call["user"]


def test_a_correct_price_is_verified_against_the_product() -> None:
    result = _one(text=DRAFT, kind="price", product_id="acme-p-2", value="1,490 EUR")
    assert (result.status, result.evidence) == ("verified", "acme-p-2")
    assert result.claim == DRAFT


def test_a_wrong_price_is_false_and_says_the_catalog_price() -> None:
    result = _one(text="Pro is 990 EUR.", kind="price", product_id="acme-p-2", value="990 EUR")
    assert (result.status, result.evidence) == ("false", "acme-p-2")
    assert "1490.00 EUR" in result.reason


def test_a_price_in_another_currency_is_false() -> None:
    result = _one(text="Pro is $1490.", kind="price", product_id="acme-p-2", value="$1490")
    assert result.status == "false"


@pytest.mark.parametrize(
    ("value", "reason"),
    [("1490", "currency"), ("about fifteen hundred", "amount"), (None, "amount")],
)
def test_a_price_that_cannot_be_read_fully_is_unknown(value: str | None, reason: str) -> None:
    result = _one(text="Pro is 1490.", kind="price", product_id="acme-p-2", value=value)
    assert result.status == "unknown"
    assert reason in result.reason


@pytest.mark.parametrize("product_id", [None, "acme-p-404"])
def test_a_price_for_no_known_product_is_unknown(product_id: str | None) -> None:
    result = _one(text="It is 49 EUR.", kind="price", product_id=product_id, value="49 EUR")
    assert (result.status, result.evidence) == ("unknown", None)


def test_a_catalog_product_name_is_verified() -> None:
    result = _one(text="Insight Enterprise", kind="product_name", value="insight  enterprise")
    assert (result.status, result.evidence) == ("verified", "acme-p-3")


def test_a_fabricated_product_is_false() -> None:
    result = _one(text="Try Insight Ultra.", kind="product_name", value="Insight Ultra")
    assert (result.status, result.evidence) == ("false", None)
    assert "Insight Ultra" in result.reason


def test_an_allowed_feature_is_verified_against_its_product() -> None:
    result = _one(text="Pro gives you full API access.", kind="feature", product_id="acme-p-2")
    assert (result.status, result.evidence) == ("verified", "acme-p-2")


def test_an_allowed_feature_without_a_product_is_looked_up_in_the_whole_catalog() -> None:
    result = _one(text="We include single sign-on.", kind="feature")
    assert (result.status, result.evidence) == ("verified", "acme-p-3")


def test_an_unlisted_feature_is_unknown_not_false() -> None:
    result = _one(text="Pro includes single sign-on.", kind="feature", product_id="acme-p-2")
    assert (result.status, result.evidence) == ("unknown", None)


def test_known_limit_a_paraphrase_of_an_allowed_feature_is_unknown() -> None:
    result = _one(text="Pro is set up in a single day.", kind="feature", product_id="acme-p-2")
    assert result.status == "unknown"


def test_other_claims_are_unknown() -> None:
    assert _one(text="We are the market leader.", kind="other").status == "unknown"


def test_checks_keep_the_order_of_the_extracted_claims() -> None:
    results, _ = _check(
        {"text": "a", "kind": "other"},
        {"text": "Insight Pro", "kind": "product_name", "value": "Insight Pro"},
    )
    assert [r.claim for r in results] == ["a", "Insight Pro"]


@pytest.mark.parametrize(
    ("value", "amount", "currency"),
    [
        ("1,490 EUR", "1490", "EUR"),
        ("1 490,00 €", "1490.00", "EUR"),
        ("€1.490", "1490", "EUR"),
        ("$120,000.50", "120000.50", "USD"),
        ("49.9 usd", "49.9", "USD"),
        ("£12", "12", "GBP"),
        ("1490", "1490", None),
        ("free", None, None),
    ],
)
def test_parse_price(value: str, amount: str | None, currency: str | None) -> None:
    parsed_amount, parsed_currency = parse_price(value)
    assert parsed_amount == (Decimal(amount) if amount else None)
    assert parsed_currency == currency
