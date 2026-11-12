"""POST /harmonize over a scripted agent, with the flow swapped in through FastAPI."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.core.domain.errors import AgentLimitError
from groundwork.core.domain.harmonize import AgentResult, HarmonizedEmail
from groundwork.core.domain.knowhow import Usage
from groundwork.core.services.harmonize import HarmonizeFlow
from groundwork.core.services.packs import load_domain_policies, load_rules
from groundwork.entrypoints.api import app, get_flow
from tests.fakes import InMemoryApproval, RecordingMessaging, ScriptedAgent, StubModel

ROOT = Path(__file__).resolve().parents[2]
ACME = ROOT / "client_packs" / "acme"
PRICE = {
    "text": "Pro costs 1490 EUR.",
    "kind": "price",
    "product_id": "acme-p-2",
    "value": "1490 EUR",
}
BODY = {"contact_id": "acme-c-1", "channel": "external", "draft": "Hi, what does Pro cost?"}


def _flow(tmp_path: Path, agent: ScriptedAgent, messaging: RecordingMessaging) -> HarmonizeFlow:
    return HarmonizeFlow(
        crm=FixtureCrm(ACME / "fixtures" / "hubspot"),
        rules=load_rules(ACME),
        agent=agent,
        model=StubModel(structured=lambda **_: {"claims": [PRICE]}),
        messaging=messaging,
        approval=InMemoryApproval(),
        policies=load_domain_policies(ROOT / "domains", "comms"),
        system="harmonize prompt",
        claims_prompt="claims prompt",
        traces_dir=tmp_path / "traces",
    )


def _result(body: str = "Insight Pro costs 1490.00 EUR.") -> AgentResult:
    return AgentResult(
        email=HarmonizedEmail(subject="Pro pricing", body=body, rationale="Catalog price."),
        usage=Usage(input_tokens=10, output_tokens=5),
    )


@pytest.fixture
def served(tmp_path: Path) -> Iterator[Any]:
    def serve(agent: ScriptedAgent) -> tuple[TestClient, RecordingMessaging]:
        messaging = RecordingMessaging()
        flow = _flow(tmp_path, agent, messaging)
        app.dependency_overrides[get_flow] = lambda: flow
        return TestClient(app), messaging

    yield serve
    app.dependency_overrides.clear()


def test_harmonize_returns_the_email_the_decision_and_the_trace_id(served: Any) -> None:
    client, messaging = served(ScriptedAgent(_result()))
    response = client.post("/harmonize", json=BODY)
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"email", "decision", "trace_id"}
    assert data["email"]["subject"] == "Pro pricing"
    assert data["decision"]["route"] == "approval"
    assert len(data["trace_id"]) == 12
    assert messaging.sent == []


def test_an_internal_email_is_sent_and_a_given_case_id_names_the_trace(served: Any) -> None:
    client, messaging = served(ScriptedAgent(_result()))
    response = client.post("/harmonize", json={**BODY, "channel": "internal", "case_id": "my-case"})
    assert response.json()["decision"]["route"] == "auto_send"
    assert response.json()["trace_id"] == "my-case"
    assert len(messaging.sent) == 1


def test_a_blocked_email_says_why_and_sends_nothing(served: Any) -> None:
    client, messaging = served(ScriptedAgent(_result("Enjoy 50% off Pro.")))
    data = client.post("/harmonize", json=BODY).json()
    assert data["decision"]["route"] == "blocked"
    assert "50% off" in data["decision"]["reasons"][0]
    assert messaging.sent == []


def test_an_unknown_contact_is_a_404_naming_it(served: Any) -> None:
    client, _ = served(ScriptedAgent(_result()))
    response = client.post("/harmonize", json={**BODY, "contact_id": "acme-c-404"})
    assert response.status_code == 404 and "acme-c-404" in response.json()["detail"]


def test_an_agent_that_goes_past_a_limit_is_a_502_with_the_limit_and_sends_nothing(
    served: Any,
) -> None:
    client, messaging = served(ScriptedAgent(error=AgentLimitError("time", "60 s")))
    response = client.post("/harmonize", json={**BODY, "channel": "internal"})
    assert response.status_code == 502
    assert "time limit exceeded" in response.json()["detail"]
    assert messaging.sent == []


@pytest.mark.parametrize(
    "body",
    [
        {**BODY, "channel": "any"},
        {**BODY, "draft": ""},
        {"channel": "internal"},
        {**BODY, "case_id": "../x"},
    ],
)
def test_an_invalid_request_is_a_422(served: Any, body: dict[str, Any]) -> None:
    client, _ = served(ScriptedAgent(_result()))
    assert client.post("/harmonize", json=body).status_code == 422


def test_a_pack_that_cannot_be_loaded_is_a_500_with_the_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROUNDWORK_PACK", "no-such-pack")
    from groundwork.entrypoints import api

    api.default_flow.cache_clear()
    try:
        response = TestClient(app).post("/harmonize", json=BODY)
    finally:
        api.default_flow.cache_clear()
    assert response.status_code == 500 and "no-such-pack" in response.json()["detail"]
