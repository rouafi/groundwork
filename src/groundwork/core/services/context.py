"""Assemble what an agent needs to know about one contact, from the CRM only.

Every field is data from the system of record. Free text such as `notes` is
returned exactly as stored: it is untrusted data, never instructions, and it is
the agent's prompt, not this service, that must treat it as such.
"""

from pydantic import BaseModel, ConfigDict

from groundwork.core.domain.facts import Company, Contact, Deal, Product
from groundwork.core.ports.crm import CrmPort


class ContactContext(BaseModel):
    """A contact, their company, their deals and the products of those deals."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contact: Contact
    company: Company
    deals: tuple[Deal, ...]
    products: tuple[Product, ...]


def contact_context(crm: CrmPort, contact_id: str) -> ContactContext:
    """The context of one contact. Products appear once, in the order the deals list them.

    Raises `NotFoundError` for an unknown contact.
    """
    contact = crm.get_contact(contact_id)
    deals = crm.get_deals(contact_id)
    product_ids = list(dict.fromkeys(pid for deal in deals for pid in deal.product_ids))
    return ContactContext(
        contact=contact,
        company=crm.get_company(contact.company_id),
        deals=deals,
        products=crm.get_products(product_ids),
    )
