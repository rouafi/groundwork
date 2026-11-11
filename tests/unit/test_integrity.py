from decimal import Decimal

from groundwork.core.domain.domain_pack import DomainDefaults, DomainPack
from groundwork.core.domain.facts import Company, Contact, Deal, Product
from groundwork.core.ports.crm import CrmPort
from groundwork.core.services.integrity import IntegrityIssue, check_integrity
from tests.fakes import InMemoryCrm

DOMAIN = DomainPack(
    segments=("smb", "enterprise"),
    personas=("economic-buyer",),
    channels=("internal", "external"),
    defaults=DomainDefaults(tone="formal"),
)
COMPANY = Company(id="co_1", name="Example Corp", segment="smb", country="FR")
CONTACT = Contact(
    id="c_1",
    first_name="Ada",
    last_name="Example",
    email="ada@example.com",
    company_id="co_1",
    persona="economic-buyer",
)
PRODUCT = Product(
    id="p_1",
    name="Pro",
    description="",
    price=Decimal(10),
    currency="EUR",
    allowed_claims=(),
)
DEAL = Deal(
    id="d_1", contact_id="c_1", name="Pro", stage="won", amount=Decimal(10), product_ids=("p_1",)
)


def _crm(
    companies: tuple[Company, ...] = (COMPANY,),
    contacts: tuple[Contact, ...] = (CONTACT,),
    deals: tuple[Deal, ...] = (DEAL,),
) -> CrmPort:
    return InMemoryCrm(companies, contacts, deals, (PRODUCT,))


def test_consistent_facts_have_no_issue() -> None:
    assert check_integrity(_crm(), DOMAIN) == ()


def test_deal_with_missing_contact_is_reported() -> None:
    orphan = DEAL.model_copy(update={"contact_id": "c_99"})
    issues = check_integrity(_crm(deals=(orphan,)), DOMAIN)
    assert issues == (IntegrityIssue("deal", "d_1", "references missing contact c_99"),)
    assert str(issues[0]) == "deal d_1 references missing contact c_99"


def test_deal_with_missing_product_is_reported() -> None:
    deal = DEAL.model_copy(update={"product_ids": ("p_1", "p_404")})
    issues = check_integrity(_crm(deals=(deal,)), DOMAIN)
    assert [str(i) for i in issues] == ["deal d_1 references missing product p_404"]


def test_contact_with_missing_company_is_reported() -> None:
    contact = CONTACT.model_copy(update={"company_id": "co_9"})
    issues = check_integrity(_crm(contacts=(contact,)), DOMAIN)
    assert [str(i) for i in issues] == ["contact c_1 references missing company co_9"]


def test_values_outside_vocabulary_are_reported() -> None:
    company = COMPANY.model_copy(update={"segment": "startup"})
    contact = CONTACT.model_copy(update={"persona": "ceo"})
    issues = check_integrity(_crm(companies=(company,), contacts=(contact,)), DOMAIN)
    assert [str(i) for i in issues] == [
        "company co_1 has segment 'startup', not in the domain vocabulary (smb, enterprise)",
        "contact c_1 has persona 'ceo', not in the domain vocabulary (economic-buyer)",
    ]
