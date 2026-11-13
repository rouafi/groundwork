"""Fakes and builders shared by the eval tests: a scripted agent per case, a stub model that
answers both the claim check and the judge, and EvalDeps over the committed acme pack."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from groundwork.adapters.agent.passthrough import PassthroughAgent
from groundwork.adapters.approval.memory import MemoryApproval
from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.adapters.messaging.memory import MemoryMessaging
from groundwork.core.domain.evals import CalibrationCase, GoldenCase, Thresholds
from groundwork.core.domain.harmonize import (
    AgentResult,
    ContextPack,
    HarmonizedEmail,
    HarmonizeRequest,
)
from groundwork.core.domain.knowhow import Usage
from groundwork.core.domain.policy import Limits
from groundwork.core.domain.search import RetrievalQuestion, SearchHit
from groundwork.core.services.evals.judge import judge_system
from groundwork.core.services.evals.runner import EvalDeps
from groundwork.core.services.harmonize import HarmonizeFlow
from groundwork.core.services.packs import load_domain_policies, load_rules
from tests.fakes import StubModel

ROOT = Path(__file__).resolve().parents[1]
ACME = ROOT / "client_packs" / "acme"
PRICE_OK = {
    "text": "Pro costs 1490 EUR.",
    "kind": "price",
    "product_id": "acme-p-2",
    "value": "1490 EUR",
}
PRICE_WRONG = {
    "text": "Pro costs 990 EUR.",
    "kind": "price",
    "product_id": "acme-p-2",
    "value": "990 EUR",
}


def email(body: str = "Insight Pro costs 1490.00 EUR.", cited: tuple[str, ...] = ()) -> AgentResult:
    return AgentResult(
        email=HarmonizedEmail(subject="Your quote", body=body, rationale="r", cited_nodes=cited),
        usage=Usage(input_tokens=900, output_tokens=120),
    )


class CaseAgent:
    """AgentPort that returns the result scripted for each case id."""

    def __init__(
        self, results: Mapping[str, AgentResult], default: AgentResult | None = None
    ) -> None:
        self._results = dict(results)
        self._default = default or email()
        self.calls: list[str] = []

    def run(
        self, *, system: str, context: ContextPack, request: HarmonizeRequest, limits: Limits
    ) -> AgentResult:
        self.calls.append(request.id)
        return self._results.get(request.id, self._default)


class EvalModel(StubModel):
    """Answers the claim check (a price in the text) and the judge (a fixed tone)."""

    def __init__(
        self, tone: int | Callable[[str], int] = 5, violations: Sequence[str] = ()
    ) -> None:
        self._tone, self._violations = tone, list(violations)
        super().__init__(structured=self._answer)

    def _answer(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs["schema"].__name__ == "JudgeVerdict":
            doc = kwargs["document"]
            tone = self._tone(doc) if callable(self._tone) else self._tone
            rules = [{"rule_id": r, "verdict": "violated", "reason": "x"} for r in self._violations]
            return {"tone": tone, "tone_reason": "Fine.", "rules": rules}
        document = kwargs["document"]
        return {"claims": [PRICE_WRONG] if "990" in document else [PRICE_OK]}


def case(id: str = "acme-001", **fields: Any) -> GoldenCase:
    base = {"id": id, "contact_id": "acme-c-1", "channel": "external", "draft": "Pro is 1490 EUR?",
            "must_contain": ["1490"], "expected_route": "approval"}  # fmt: skip
    return GoldenCase.model_validate({**base, **fields})


def calibration(*pairs: tuple[int, int]) -> list[CalibrationCase]:
    return [
        CalibrationCase(id=f"cal-{i}", subject="s", body=f"body {i}", human_tone=h)
        for i, (h, _) in enumerate(pairs)
    ]


def deps(
    cases: Sequence[GoldenCase],
    agent: CaseAgent,
    model: EvalModel,
    thresholds: Thresholds | None = None,
    calibration_cases: Sequence[CalibrationCase] | None = None,
    questions: Sequence[RetrievalQuestion] = (),
    search: Callable[[str], Sequence[SearchHit]] | None = None,
    traces_dir: Path | None = None,
) -> EvalDeps:
    rules = tuple(r for r in load_rules(ACME) if r.status == "approved")
    crm = FixtureCrm(ACME / "fixtures" / "hubspot")
    flow = HarmonizeFlow(
        crm=crm, rules=rules, agent=agent, model=model,
        messaging=MemoryMessaging(), approval=MemoryApproval(),
        policies=load_domain_policies(ROOT / "domains", "comms"),
        system="harmonize prompt", claims_prompt="claims prompt",
        traces_dir=traces_dir or ROOT / "unused", internal_recipient="handoffs@acme.example",
        write_traces=False,
    )  # fmt: skip
    raw = HarmonizeFlow(**{**flow.__dict__, "agent": PassthroughAgent(), "search": None})
    known = frozenset({r.id for r in rules} | set(crm.list_product_ids()))
    cal = calibration_cases if calibration_cases is not None else calibration((5, 5), (4, 4))
    return EvalDeps(
        pack="acme", cases=cases, thresholds=thresholds or Thresholds(), calibration=cal,
        flow=flow, raw_flow=raw, judge_model=model, judge_system=judge_system("Judge.", "Rubric."),
        rules=rules, known_nodes=known, questions=questions, search=search,
    )  # fmt: skip
