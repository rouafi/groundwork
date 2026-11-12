from pathlib import Path

from groundwork.adapters.agent.passthrough import SUBJECT, PassthroughAgent
from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.core.domain.harmonize import ContextPack, HarmonizeRequest
from groundwork.core.domain.policy import Limits
from groundwork.core.services.harmonize import HarmonizeFlow, harmonize
from groundwork.core.services.packs import load_domain_policies, load_rules
from tests.fakes import InMemoryApproval, RecordingMessaging, StubModel

ROOT = Path(__file__).resolve().parents[2]
ACME = ROOT / "client_packs" / "acme"
DRAFT = "Hi Malo, here is 50% off the Onboarding Pack, so 400 EUR instead of 800."
WRONG_PRICE = {"text": "400 EUR", "kind": "price", "product_id": "acme-p-4", "value": "400 EUR"}


def test_the_draft_goes_through_unchanged_with_no_step_and_no_cost(pack: ContextPack) -> None:
    request = HarmonizeRequest(contact_id="acme-c-4", channel="external", draft=DRAFT)
    result = PassthroughAgent().run(system="s", context=pack, request=request, limits=Limits())
    assert result.email.body == DRAFT and result.email.subject == SUBJECT
    assert result.steps == () and result.usage.input_tokens == 0


def test_the_harness_blocks_what_a_faulty_agent_lets_through(tmp_path: Path) -> None:
    messaging, approval = RecordingMessaging(), InMemoryApproval()
    flow = HarmonizeFlow(
        crm=FixtureCrm(ACME / "fixtures" / "hubspot"),
        rules=load_rules(ACME),
        agent=PassthroughAgent(),
        model=StubModel(structured=lambda **_: {"claims": [WRONG_PRICE]}),
        messaging=messaging,
        approval=approval,
        policies=load_domain_policies(ROOT / "domains", "comms"),
        system="s",
        claims_prompt="c",
        traces_dir=tmp_path,
    )
    outcome = harmonize(
        flow, HarmonizeRequest(contact_id="acme-c-4", channel="external", draft=DRAFT)
    )
    assert outcome.decision.route == "blocked"
    reasons = " ".join(outcome.decision.reasons)
    assert "false claim" in reasons and "forbidden pattern" in reasons and "50% off" in reasons
    assert messaging.sent == [] and approval.list_pending() == ()
