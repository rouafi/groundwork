from pathlib import Path

import pytest

from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.core.domain.facts import ContactContext
from groundwork.core.domain.knowhow import Rule
from groundwork.core.domain.search import SearchHit
from groundwork.core.services.context import contact_context
from groundwork.core.services.context_pack import (
    DEFAULT_BUDGET,
    build_context_pack,
    estimate_tokens,
)
from groundwork.core.services.packs import load_rules

ACME = Path(__file__).resolve().parents[2] / "client_packs" / "acme"


@pytest.fixture(scope="module")
def context() -> ContactContext:
    return contact_context(FixtureCrm(ACME / "fixtures" / "hubspot"), "acme-c-1")


@pytest.fixture(scope="module")
def rules() -> tuple[Rule, ...]:
    return load_rules(ACME)


def _hits(count: int, size: int = 400) -> tuple[SearchHit, ...]:
    return tuple(
        SearchHit(chunk_id=f"d-c-{i}", doc_id="d", text="x" * size, score=1.0 / (i + 1))
        for i in range(count)
    )


def test_a_token_is_four_characters_rounded_up() -> None:
    assert [estimate_tokens(t) for t in ("", "a", "abcd", "abcde")] == [0, 1, 1, 2]


def test_a_roomy_budget_keeps_everything_and_truncates_nothing(
    context: ContactContext, rules: tuple[Rule, ...]
) -> None:
    pack = build_context_pack(context, rules, _hits(3), "external")
    assert pack.truncated == ()
    assert len(pack.passages) == 3
    assert 0 < pack.estimated_tokens <= DEFAULT_BUDGET
    assert pack.contact_context == context


def test_only_approved_applicable_rules_are_kept_most_specific_first(
    context: ContactContext, rules: tuple[Rule, ...]
) -> None:
    pack = build_context_pack(context, rules, (), "external")
    assert pack.rules
    assert all(
        r.status == "approved" and r.scope.channel in ("any", "external") for r in pack.rules
    )
    keys = [-r.scope.specificity for r in pack.rules]
    assert keys == sorted(keys)


def test_passages_are_dropped_before_any_rule(
    context: ContactContext, rules: tuple[Rule, ...]
) -> None:
    roomy = build_context_pack(context, rules, (), "external")
    budget = roomy.estimated_tokens + 150  # room for one 400-character passage only
    pack = build_context_pack(context, rules, _hits(4), "external", budget=budget)
    assert pack.rules == roomy.rules
    assert [p.chunk_id for p in pack.passages] == ["d-c-0"]
    assert pack.truncated == ("passage d-c-1", "passage d-c-2", "passage d-c-3")
    assert pack.estimated_tokens <= budget


def test_the_least_specific_rules_go_next_and_facts_stay(
    context: ContactContext, rules: tuple[Rule, ...]
) -> None:
    roomy = build_context_pack(context, rules, (), "external")
    budget = roomy.estimated_tokens - 100
    pack = build_context_pack(context, rules, _hits(2), "external", budget=budget)
    assert len(pack.rules) < len(roomy.rules)
    assert pack.rules == roomy.rules[: len(pack.rules)]
    dropped = [t for t in pack.truncated if t.startswith("rule ")]
    assert dropped == [f"rule {r.id}" for r in roomy.rules[len(pack.rules) :]]
    assert not pack.passages
    assert pack.contact_context == context
    assert pack.estimated_tokens <= budget


def test_facts_are_never_truncated_even_over_budget(
    context: ContactContext, rules: tuple[Rule, ...]
) -> None:
    pack = build_context_pack(context, rules, _hits(2), "external", budget=10)
    assert pack.contact_context == context
    assert pack.rules == () and pack.passages == ()
    assert pack.truncated[0].startswith("facts alone use")
    assert pack.estimated_tokens > 10


def test_the_pack_is_deterministic(context: ContactContext, rules: tuple[Rule, ...]) -> None:
    first = build_context_pack(context, rules, _hits(3), "internal", budget=900)
    assert first == build_context_pack(context, rules, _hits(3), "internal", budget=900)


def test_the_estimate_is_the_sum_of_what_is_kept(
    context: ContactContext, rules: tuple[Rule, ...]
) -> None:
    pack = build_context_pack(context, rules, _hits(2), "external")
    parts = [pack.contact_context, *pack.rules, *pack.passages]
    assert pack.estimated_tokens == sum(estimate_tokens(p.model_dump_json()) for p in parts)
