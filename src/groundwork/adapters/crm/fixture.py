"""FixtureCrm: a CrmPort backed by HubSpot-shaped JSON files in a client pack.

Reads `companies.json`, `contacts.json`, `deals.json` and `products.json`
from one folder. Each file is a JSON array of HubSpot CRM v3 objects. The
files are read once, at construction; the adapter never writes.
"""

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from groundwork.adapters.crm.hubspot_mapping import (
    MappingError,
    to_company,
    to_contact,
    to_deal,
    to_product,
)
from groundwork.core.domain.errors import NotFoundError, PackError
from groundwork.core.domain.facts import Company, Contact, Deal, Product

FILES = {
    "company": "companies.json",
    "contact": "contacts.json",
    "deal": "deals.json",
    "product": "products.json",
}


class _Identified(Protocol):
    @property
    def id(self) -> str: ...


class FixtureCrm:
    """Read-only CRM over local fixture files. Raises `PackError` on unreadable data."""

    def __init__(self, fixtures_dir: Path) -> None:
        self._companies = _load(fixtures_dir / FILES["company"], to_company)
        self._contacts = _load(fixtures_dir / FILES["contact"], to_contact)
        self._deals = _load(fixtures_dir / FILES["deal"], to_deal)
        self._products = _load(fixtures_dir / FILES["product"], to_product)

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


def _load[T: _Identified](path: Path, mapper: Callable[[object], T]) -> dict[str, T]:
    entries = _read_array(path)
    items: dict[str, T] = {}
    for entry in entries:
        try:
            item = mapper(entry)
        except MappingError as exc:
            raise PackError(f"{path}: {exc}") from exc
        if item.id in items:
            raise PackError(f"{path}: duplicate id {item.id}")
        items[item.id] = item
    return items


def _read_array(path: Path) -> list[object]:
    if not path.is_file():
        raise PackError(f"{path}: file not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PackError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(data, list):
        raise PackError(f"{path}: expected a JSON array of HubSpot objects")
    return data


def _get[T](items: dict[str, T], kind: str, id: str) -> T:
    try:
        return items[id]
    except KeyError:
        raise NotFoundError(kind, id) from None
