"""In-memory CrmPort for tests of the core. Not an adapter: it lives with the tests."""

from collections.abc import Iterable, Sequence

from groundwork.core.domain.errors import NotFoundError
from groundwork.core.domain.facts import Company, Contact, Deal, Product


class InMemoryCrm:
    def __init__(
        self,
        companies: Iterable[Company] = (),
        contacts: Iterable[Contact] = (),
        deals: Iterable[Deal] = (),
        products: Iterable[Product] = (),
    ) -> None:
        self._companies = {c.id: c for c in companies}
        self._contacts = {c.id: c for c in contacts}
        self._deals = {d.id: d for d in deals}
        self._products = {p.id: p for p in products}

    def get_contact(self, contact_id: str) -> Contact:
        return _get(self._contacts, "contact", contact_id)

    def get_company(self, company_id: str) -> Company:
        return _get(self._companies, "company", company_id)

    def get_deal(self, deal_id: str) -> Deal:
        return _get(self._deals, "deal", deal_id)

    def get_deals(self, contact_id: str) -> tuple[Deal, ...]:
        self.get_contact(contact_id)
        return tuple(d for d in self._deals.values() if d.contact_id == contact_id)

    def get_products(self, product_ids: Sequence[str]) -> tuple[Product, ...]:
        return tuple(_get(self._products, "product", pid) for pid in product_ids)

    def list_contact_ids(self) -> tuple[str, ...]:
        return tuple(self._contacts)

    def list_company_ids(self) -> tuple[str, ...]:
        return tuple(self._companies)

    def list_deal_ids(self) -> tuple[str, ...]:
        return tuple(self._deals)

    def list_product_ids(self) -> tuple[str, ...]:
        return tuple(self._products)


def _get[T](items: dict[str, T], kind: str, id: str) -> T:
    try:
        return items[id]
    except KeyError:
        raise NotFoundError(kind, id) from None
