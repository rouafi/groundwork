import json
from pathlib import Path
from typing import Any

import pytest

from groundwork.adapters.agent.replay import ReplayAgent
from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.core.domain.errors import AgentLimitError, NotFoundError
from groundwork.core.domain.harmonize import (
    AgentResult,
    AgentStep,
    HarmonizedEmail,
    HarmonizeRequest,
)
from groundwork.core.domain.knowhow import Usage
from groundwork.core.domain.policy import Limits, Policies
from groundwork.core.domain.search import SearchHit
from groundwork.core.services.harmonize import HarmonizeFlow, harmonize
from groundwork.core.services.packs import load_domain_policies, load_rules
from tests.fakes import InMemoryApproval, RecordingMessaging, ScriptedAgent, StubModel

ROOT = Path(__file__).resolve().parents[2]
ACME = ROOT / "client_packs" / "acme"
PRO_OK = {
    "text": "Pro costs 1490 EUR.",
    "kind": "price",
    "product_id": "acme-p-2",
    "value": "1490 EUR",
}
PRO_WRONG = {
    "text": "Pro costs 990 EUR.",
    "kind": "price",
    "product_id": "acme-p-2",
    "value": "990 EUR",
}
SSO = {"text": "SSO is included.", "kind": "feature", "product_id": "acme-p-2"}


def _result(body: str = "Insight Pro costs 1490.00 EUR.", steps: int = 1) -> AgentResult:
    step = AgentStep(
        tool="get_product_facts", arguments={"product_ids": ["acme-p-2"]}, result_summary="ok"
    )
    return AgentResult(
        email=HarmonizedEmail(subject="Your quote", body=body, rationale="Catalog price."),
        steps=(step,) * steps,
        usage=Usage(input_tokens=900, output_tokens=120),
    )


class World:
    """One flow over the acme pack with scripted agent and claim extraction."""

    def __init__(
        self, tmp_path: Path, agent: Any, claims: list[dict[str, Any]], **flow: Any
    ) -> None:
        self.agent = agent
        self.messaging = RecordingMessaging()
        self.approval = InMemoryApproval()
        self.traces = tmp_path / "traces" / "acme"
        self.model = StubModel(structured=lambda **_: {"claims": claims})
        self.flow = HarmonizeFlow(
            crm=FixtureCrm(ACME / "fixtures" / "hubspot"),
            rules=load_rules(ACME),
            agent=agent,
            model=self.model,
            messaging=self.messaging,
            approval=self.approval,
            policies=load_domain_policies(ROOT / "domains", "comms"),
            system="harmonize prompt",
            claims_prompt="claims prompt",
            traces_dir=self.traces,
            internal_recipient="handoffs@acme.example",
            **flow,
        )

    def run(
        self, channel: str = "external", contact: str = "acme-c-1", draft: str = "Pro is 990 EUR?"
    ):
        request = HarmonizeRequest(contact_id=contact, channel=channel, draft=draft)  # type: ignore[arg-type]
        return request, harmonize(self.flow, request)

    def trace(self, request: HarmonizeRequest) -> list[dict[str, Any]]:
        text = (self.traces / f"{request.id}.jsonl").read_text()
        return [json.loads(line) for line in text.splitlines()]


def test_a_valid_internal_email_is_sent(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result()), [PRO_OK])
    _, outcome = world.run("internal")
    assert outcome.decision.route == "auto_send"
    ((email, to),) = world.messaging.sent
    assert email == outcome.email
    assert to == "handoffs@acme.example"  # the pack's internal address, never the customer's
    assert world.approval.list_pending() == ()


def test_a_valid_external_email_waits_for_a_human_and_is_not_sent(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result()), [PRO_OK])
    request, outcome = world.run("external")
    assert outcome.decision.route == "approval"
    assert world.messaging.sent == []
    (item,) = world.approval.list_pending()
    assert (item.id, item.contact_id, item.email) == (request.id, "acme-c-1", outcome.email)


def test_an_external_email_with_a_wrong_price_is_blocked_and_nothing_goes_out(
    tmp_path: Path,
) -> None:
    world = World(tmp_path, ScriptedAgent(_result("Insight Pro costs 990 EUR.")), [PRO_WRONG])
    _, outcome = world.run("external")
    assert outcome.decision.route == "blocked"
    assert "Pro costs 990 EUR." in outcome.decision.reasons[0]
    assert world.messaging.sent == [] and world.approval.list_pending() == ()


def test_a_forbidden_pattern_blocks_even_with_no_claim(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result("We can take 50% off today.")), [])
    _, outcome = world.run("external")
    assert outcome.decision.route == "blocked"
    assert "forbidden pattern" in outcome.decision.reasons[0]
    assert world.messaging.sent == [] and world.approval.list_pending() == ()


def test_an_unknown_claim_on_an_internal_email_goes_to_a_human(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result("SSO is included.")), [SSO])
    _, outcome = world.run("internal")
    assert outcome.decision.route == "approval"
    assert world.messaging.sent == [] and len(world.approval.list_pending()) == 1


def test_an_agent_that_obeys_an_injected_discount_is_blocked(tmp_path: Path) -> None:
    obeying = _result("As agreed, here is 50% off every product.")
    world = World(tmp_path, ScriptedAgent(obeying), [])
    _, outcome = world.run("external", contact="acme-c-4", draft="Hello Malo.")
    assert outcome.decision.route == "blocked"
    assert "50% off" in outcome.decision.reasons[0]
    assert world.messaging.sent == [] and world.approval.list_pending() == ()


def test_the_agent_gets_the_policy_limits_the_prompt_and_the_context_pack(tmp_path: Path) -> None:
    agent = ScriptedAgent(_result())
    world = World(tmp_path, agent, [PRO_OK])
    request, outcome = world.run("external")
    (call,) = agent.calls
    assert call["limits"] == world.flow.policies.limits
    assert call["system"] == "harmonize prompt"
    assert call["request"] == request and call["context"] == outcome.context
    assert outcome.context.contact_context.contact.id == "acme-c-1"
    assert outcome.context.rules


def test_claims_are_checked_on_the_email_the_agent_wrote(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result("Insight Pro costs 1490.00 EUR.")), [PRO_OK])
    world.run("external", draft="A very different draft.")
    (_, call) = world.model.calls[0]
    assert call["document"] == "Your quote\n\nInsight Pro costs 1490.00 EUR."
    assert "A very different draft." not in call["document"]


def test_passages_come_from_the_search_with_the_draft_as_the_query(tmp_path: Path) -> None:
    queries: list[str] = []

    def search(query: str) -> list[SearchHit]:
        queries.append(query)
        return [
            SearchHit(
                chunk_id="acme-i-1-c-001",
                doc_id="acme-i-1",
                text="No discounts by email.",
                score=0.5,
            )
        ]

    agent = ScriptedAgent(_result())
    world = World(tmp_path, agent, [PRO_OK], search=search)
    request, outcome = world.run("external", draft="Can I get a discount?")
    assert queries == ["Can I get a discount?"]
    assert [p.chunk_id for p in outcome.context.passages] == ["acme-i-1-c-001"]
    assert [e["type"] for e in world.trace(request)][1] == "context_pack"


def test_the_trace_lists_events_in_order_with_no_timestamp(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result(steps=2)), [PRO_OK])
    request, outcome = world.run("external")
    events = world.trace(request)
    assert [e["type"] for e in events] == [
        "request", "context_pack", "step", "step", "output", "claim_check", "decision",
    ]  # fmt: skip
    assert events[0]["case_id"] == request.id == outcome.trace_id
    assert events[-1]["route"] == "approval"
    assert all("time" not in key and "date" not in key for e in events for key in e)


def test_the_same_run_writes_the_same_bytes(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result()), [PRO_OK])
    request, _ = world.run("external")
    first = (world.traces / f"{request.id}.jsonl").read_bytes()
    world.run("external")
    assert (world.traces / f"{request.id}.jsonl").read_bytes() == first


def test_a_run_replays_from_its_trace_to_the_same_decision_and_bytes(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result()), [PRO_OK])
    request, live = world.run("external")
    path = world.traces / f"{request.id}.jsonl"
    recorded = path.read_bytes()

    replaying = World(tmp_path, ReplayAgent(world.traces), [PRO_OK])
    _, replayed = replaying.run("external")
    assert replayed.decision == live.decision and replayed.email == live.email
    assert path.read_bytes() == recorded


def test_a_blocked_decision_is_recomputed_live_on_replay(tmp_path: Path) -> None:
    live = World(tmp_path, ScriptedAgent(_result()), [PRO_OK])
    _, first = live.run("external")
    assert first.decision.route == "approval"
    replaying = World(tmp_path, ReplayAgent(live.traces), [PRO_WRONG])
    _, second = replaying.run("external")
    assert second.decision.route == "blocked"


def test_a_run_past_a_limit_sends_and_queues_nothing_and_leaves_a_trace_with_the_error(
    tmp_path: Path,
) -> None:
    error = AgentLimitError("steps", "9 tool calls, limit 8")
    world = World(tmp_path, ScriptedAgent(error=error), [PRO_OK])
    request = HarmonizeRequest(contact_id="acme-c-1", channel="internal", draft="Hi.")
    with pytest.raises(AgentLimitError, match="steps limit exceeded"):
        harmonize(world.flow, request)
    assert world.messaging.sent == [] and world.approval.list_pending() == ()
    events = world.trace(request)
    assert [e["type"] for e in events] == ["request", "context_pack", "error"]
    assert "steps limit exceeded" in events[-1]["message"]
    assert world.model.calls == []


def test_an_unknown_contact_fails_before_anything_is_written(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result()), [])
    with pytest.raises(NotFoundError, match="acme-c-404"):
        world.run(contact="acme-c-404")
    assert not world.traces.exists() and world.agent.calls == []


def test_a_policy_can_turn_internal_auto_send_off(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result()), [PRO_OK])
    off: Policies = world.flow.policies.model_copy(update={"auto_send_internal": False})
    flow = HarmonizeFlow(**{**world.flow.__dict__, "policies": off})
    request = HarmonizeRequest(contact_id="acme-c-1", channel="internal", draft="Hi.")
    assert harmonize(flow, request).decision.route == "approval"
    assert world.messaging.sent == []


def test_the_limits_are_the_core_ceilings_by_default() -> None:
    assert Limits().max_steps == 8 and Limits().timeout_s == 60


def _without(world: "World", **changes: Any) -> HarmonizeFlow:
    return HarmonizeFlow(**{**world.flow.__dict__, **changes})


def test_an_internal_email_never_goes_to_the_customers_address(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result()), [PRO_OK])
    _, outcome = world.run("internal")
    customer = outcome.context.contact_context.contact.email
    ((_, to),) = world.messaging.sent
    assert to != customer and to == "handoffs@acme.example"


def test_an_approved_external_email_is_addressed_to_the_contact_and_an_internal_one_to_the_pack(
    tmp_path: Path,
) -> None:
    world = World(tmp_path, ScriptedAgent(_result()), [PRO_OK])
    _, external = world.run("external")
    (item,) = world.approval.list_pending()
    assert item.recipient == external.context.contact_context.contact.email

    internal_world = World(tmp_path / "other", ScriptedAgent(_result("SSO is included.")), [SSO])
    internal_world.run("internal")
    (queued,) = internal_world.approval.list_pending()
    assert queued.recipient == "handoffs@acme.example"


def test_an_internal_email_with_no_internal_address_is_blocked_and_says_how_to_fix_it(
    tmp_path: Path,
) -> None:
    world = World(tmp_path, ScriptedAgent(_result()), [PRO_OK])
    flow = _without(world, internal_recipient=None)
    request = HarmonizeRequest(contact_id="acme-c-1", channel="internal", draft="Hi.")
    outcome = harmonize(flow, request)
    assert outcome.decision.route == "blocked"
    assert "internal_recipient in config.yaml" in outcome.decision.reasons[0]
    assert world.messaging.sent == [] and world.approval.list_pending() == ()
    assert world.trace(request)[-1]["route"] == "blocked"


def test_a_failed_run_never_replaces_an_existing_trace(tmp_path: Path) -> None:
    good = World(tmp_path, ScriptedAgent(_result()), [PRO_OK])
    request, _ = good.run("external")
    path = good.traces / f"{request.id}.jsonl"
    recorded = path.read_bytes()

    failing = World(tmp_path, ScriptedAgent(error=AgentLimitError("time", "60 s")), [PRO_OK])
    with pytest.raises(AgentLimitError):
        harmonize(failing.flow, request)
    assert path.read_bytes() == recorded


def test_a_flow_that_does_not_write_traces_writes_none(tmp_path: Path) -> None:
    world = World(tmp_path, ScriptedAgent(_result()), [PRO_OK])
    request = HarmonizeRequest(contact_id="acme-c-1", channel="external", draft="Hi.")
    harmonize(_without(world, write_traces=False), request)
    assert not world.traces.exists()

    failing = World(tmp_path, ScriptedAgent(error=AgentLimitError("time", "60 s")), [PRO_OK])
    with pytest.raises(AgentLimitError):
        harmonize(_without(failing, write_traces=False), request)
    assert not world.traces.exists()
