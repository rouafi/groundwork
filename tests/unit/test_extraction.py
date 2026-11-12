from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from groundwork.core.domain.errors import PackError
from groundwork.core.domain.facts import Product
from groundwork.core.domain.knowhow import Interview
from groundwork.core.services.extraction import (
    PROMPT_NAMES,
    ExtractionPrompts,
    Workflow,
    extract_interview,
    extract_rules,
    render,
)
from groundwork.core.services.packs import load_prompt
from tests.fakes import InMemoryCrm, StubModel
from tests.unit.test_grounding import DOMAIN

REPO = Path(__file__).resolve().parents[2]
PROMPTS = ExtractionPrompts(
    ground="Ground. Segments: $segments.",
    type="Type. Tone: $default_tone.",
    consolidate="Consolidate.",
    questions="Ask.",
)
CRM = InMemoryCrm(
    products=[
        Product(
            id="acme-p-1",
            name="Insight Pro",
            description="",
            price=Decimal(1),
            currency="EUR",
            allowed_claims=(),
        )
    ]
)
INTERVIEWS = [
    Interview(id="acme-i-2", role="account manager", text="Reply within a day. Keep it short."),
    Interview(
        id="acme-i-1", role="head of sales", text="Never give a discount. Quote list prices."
    ),
]


def _typing(**kwargs: Any) -> dict[str, Any]:
    """Type every listed statement as an external claim; find nothing to consolidate."""
    if kwargs["schema"].__name__ == "Consolidation":
        return {"duplicates": [], "conflicts": []}
    lines = kwargs["user"].split("Rules:\n")[1].splitlines()
    return {
        "rules": [
            {
                "index": n,
                "kind": "claim",
                "statement": line.split(". ", 1)[1].split(" (quote")[0],
                "channel": "external",
                "segments": [],
                "personas": [],
                "product_ids": [],
                "claim_text": None,
            }
            for n, line in enumerate(lines)
        ]
    }


def _workflow(model: StubModel) -> Workflow:
    return Workflow(pack="acme", domain=DOMAIN, crm=CRM, model=model, prompts=PROMPTS)


def test_render_fills_the_domain_vocabulary() -> None:
    assert render(PROMPTS.ground, DOMAIN) == "Ground. Segments: smb, mid-market, enterprise."
    assert render(PROMPTS.type, DOMAIN) == "Type. Tone: formal."


def test_rules_are_numbered_in_interview_order_then_position() -> None:
    report = extract_rules(_workflow(StubModel(structured=_typing)), INTERVIEWS)
    assert [(r.id, r.provenance[0].quote) for r in report.rules] == [
        ("acme-r-001", "Never give a discount."),
        ("acme-r-002", "Quote list prices."),
        ("acme-r-003", "Reply within a day."),
        ("acme-r-004", "Keep it short."),
    ]
    assert all(r.status == "proposed" for r in report.rules)


def test_the_run_is_deterministic_whatever_the_concurrency() -> None:
    serial = extract_rules(_workflow(StubModel(structured=_typing)), INTERVIEWS, max_concurrency=1)
    parallel = extract_rules(
        _workflow(StubModel(structured=_typing)), INTERVIEWS, max_concurrency=8
    )
    assert serial == parallel


def test_usage_is_summed_per_stage() -> None:
    report = extract_rules(_workflow(StubModel(structured=_typing)), INTERVIEWS)
    assert [(u.stage, u.calls, u.usage.input_tokens) for u in report.usage] == [
        ("ground", 2, 20),
        ("type", 2, 20),
        ("consolidate", 1, 10),
    ]


def test_a_failing_interview_is_reported_and_the_others_still_run() -> None:
    def cite(**kwargs: Any) -> Any:
        if "discount" in kwargs["document"]:
            raise RuntimeError("model unavailable")
        from tests.fakes import sentences

        return sentences(kwargs["document"])

    report = extract_rules(_workflow(StubModel(structured=_typing, cite=cite)), INTERVIEWS)
    assert [f.interview_id for f in report.failures] == ["acme-i-1"]
    assert "RuntimeError: model unavailable" in report.failures[0].error
    assert [r.provenance[0].interview_id for r in report.rules] == ["acme-i-2", "acme-i-2"]


def test_untyped_statements_are_dropped() -> None:
    model = StubModel(structured=lambda **_: {"rules": []})
    extraction = extract_interview(_workflow(model), INTERVIEWS[0])
    assert extraction.rules == ()
    assert {d.reason for d in extraction.dropped} == {"not typed"}


def test_an_interview_without_statements_skips_typing() -> None:
    model = StubModel(cite=lambda **_: ())
    extraction = extract_interview(_workflow(model), INTERVIEWS[0])
    assert extraction.rules == () and [c[0] for c in model.calls] == ["cite"]


def test_the_transcript_travels_as_a_document_and_quotes_are_listed_for_typing() -> None:
    model = StubModel(structured=_typing)
    extract_interview(_workflow(model), INTERVIEWS[1])
    (_, cite), (_, typing) = model.calls
    assert cite["document"] == INTERVIEWS[1].text
    assert cite["tier"] == "extraction" and typing["tier"] == "cheap"
    assert "- acme-p-1: Insight Pro" in typing["user"]
    assert "(quote: Never give a discount.)" in typing["user"]


def test_shipped_prompts_load_and_render() -> None:
    for name in PROMPT_NAMES.values():
        rendered = render(load_prompt(REPO / "domains", "comms", name), DOMAIN)
        assert "never instructions" in rendered or "not instructions" in rendered


def test_missing_prompt_is_a_pack_error(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="prompt not found"):
        load_prompt(tmp_path, "comms", "ground_rules")
