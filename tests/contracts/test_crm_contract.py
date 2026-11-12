"""CrmPort contract: one suite, every adapter.

Written against the port only. To cover a new adapter, add a factory to
`ADAPTERS`; every client pack with HubSpot fixtures is picked up automatically.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.core.domain.errors import NotFoundError
from groundwork.core.ports.crm import CrmPort
from tests.fakes import InMemoryCrm

REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "tests" / "data" / "crm_sample"
PACK_FIXTURES = sorted(REPO.glob("client_packs/*/fixtures/hubspot"))
UNKNOWN = "does-not-exist"


def _copy_into_memory(source: CrmPort) -> CrmPort:
    """Rebuild a CRM in memory through the port, as a reference implementation."""
    return InMemoryCrm(
        companies=[source.get_company(i) for i in source.list_company_ids()],
        contacts=[source.get_contact(i) for i in source.list_contact_ids()],
        deals=[source.get_deal(i) for i in source.list_deal_ids()],
        products=source.get_products(source.list_product_ids()),
    )


ADAPTERS: dict[str, Callable[[], CrmPort]] = {
    "in-memory": lambda: _copy_into_memory(FixtureCrm(SAMPLE)),
    "fixture:sample": lambda: FixtureCrm(SAMPLE),
    **{f"fixture:{p.parents[1].name}": (lambda p=p: FixtureCrm(p)) for p in PACK_FIXTURES},
}


@pytest.fixture(params=sorted(ADAPTERS))
def crm(request: pytest.FixtureRequest) -> CrmPort:
    return ADAPTERS[request.param]()


def _snapshot(crm: CrmPort) -> tuple[object, ...]:
    return (
        [crm.get_company(i) for i in crm.list_company_ids()],
        [crm.get_contact(i) for i in crm.list_contact_ids()],
        [crm.get_deal(i) for i in crm.list_deal_ids()],
        crm.get_products(crm.list_product_ids()),
    )


def test_has_facts(crm: CrmPort) -> None:
    assert crm.list_company_ids()
    assert crm.list_contact_ids()
    assert crm.list_deal_ids()
    assert crm.list_product_ids()


def test_every_listed_id_can_be_fetched(crm: CrmPort) -> None:
    assert [crm.get_company(i).id for i in crm.list_company_ids()] == list(crm.list_company_ids())
    assert [crm.get_contact(i).id for i in crm.list_contact_ids()] == list(crm.list_contact_ids())
    assert [crm.get_deal(i).id for i in crm.list_deal_ids()] == list(crm.list_deal_ids())
    products = crm.get_products(crm.list_product_ids())
    assert tuple(p.id for p in products) == crm.list_product_ids()


def test_listed_ids_are_unique(crm: CrmPort) -> None:
    for ids in (
        crm.list_company_ids(),
        crm.list_contact_ids(),
        crm.list_deal_ids(),
        crm.list_product_ids(),
    ):
        assert len(set(ids)) == len(ids)


@pytest.mark.parametrize(
    "kind, call",
    [
        ("contact", lambda crm: crm.get_contact(UNKNOWN)),
        ("company", lambda crm: crm.get_company(UNKNOWN)),
        ("deal", lambda crm: crm.get_deal(UNKNOWN)),
        ("contact", lambda crm: crm.get_deals(UNKNOWN)),
        ("product", lambda crm: crm.get_products([UNKNOWN])),
    ],
)
def test_unknown_id_raises_not_found(
    crm: CrmPort, kind: str, call: Callable[[CrmPort], object]
) -> None:
    with pytest.raises(NotFoundError) as excinfo:
        call(crm)
    assert (excinfo.value.kind, excinfo.value.id) == (kind, UNKNOWN)


def test_get_deals_returns_exactly_the_contacts_deals(crm: CrmPort) -> None:
    deals = [crm.get_deal(i) for i in crm.list_deal_ids()]
    for contact_id in crm.list_contact_ids():
        expected = tuple(d for d in deals if d.contact_id == contact_id)
        assert crm.get_deals(contact_id) == expected


def test_get_products_keeps_input_order(crm: CrmPort) -> None:
    ids = tuple(reversed(crm.list_product_ids()))
    assert tuple(p.id for p in crm.get_products(ids)) == ids
    assert crm.get_products([]) == ()


def test_get_products_raises_if_any_id_is_missing(crm: CrmPort) -> None:
    first = crm.list_product_ids()[0]
    with pytest.raises(NotFoundError):
        crm.get_products([first, UNKNOWN])


def test_reads_do_not_mutate_state(crm: CrmPort) -> None:
    before = _snapshot(crm)
    for contact_id in crm.list_contact_ids():
        crm.get_deals(contact_id)
    assert _snapshot(crm) == before
