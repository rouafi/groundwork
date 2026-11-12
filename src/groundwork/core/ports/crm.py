"""CrmPort: read-only access to the client's CRM facts.

Contract (tests/contracts/test_crm_contract.py, run against every adapter):
- An unknown id raises `NotFoundError`.
- `get_deals` returns an empty tuple when the contact has no deal.
- `get_products` keeps the input order and raises if any id is missing.
- Every id returned by a `list_*` method can be fetched with the matching `get_*`.
- No method mutates state.
"""

from collections.abc import Sequence
from typing import Protocol

from groundwork.core.domain.facts import Company, Contact, Deal, Product


class CrmPort(Protocol):
    """What the core may ask a CRM. Adapters translate vendor formats into domain types."""

    def get_contact(self, contact_id: str) -> Contact:
        """Return one contact."""

    def get_company(self, company_id: str) -> Company:
        """Return one company."""

    def get_deal(self, deal_id: str) -> Deal:
        """Return one deal."""

    def get_deals(self, contact_id: str) -> tuple[Deal, ...]:
        """Return the deals of an existing contact, possibly none."""

    def get_products(self, product_ids: Sequence[str]) -> tuple[Product, ...]:
        """Return the products in the order of `product_ids`."""

    def list_contact_ids(self) -> tuple[str, ...]:
        """Return the id of every contact."""

    def list_company_ids(self) -> tuple[str, ...]:
        """Return the id of every company."""

    def list_deal_ids(self) -> tuple[str, ...]:
        """Return the id of every deal."""

    def list_product_ids(self) -> tuple[str, ...]:
        """Return the id of every product."""
