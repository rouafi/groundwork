"""Assemble the context pack an agent starts from, within a token budget.

Priority, highest first: the contact's facts (contact, company, deals, products), then
the rules that apply, most specific first, then passages from the interviews. When the
pack is over budget, passages go first, then the least specific rules. Facts are never
truncated: if they alone exceed the budget the pack says so and keeps them.

Tokens are estimated as `len(text) / 4`, rounded up: deterministic and good enough to
bound a prompt. Everything here is plain data, none of it instructions.
"""

from collections.abc import Callable, Sequence

from pydantic import BaseModel

from groundwork.core.domain.facts import ContactContext
from groundwork.core.domain.harmonize import ContextPack, MessageChannel
from groundwork.core.domain.knowhow import Rule
from groundwork.core.domain.search import SearchHit
from groundwork.core.services.rules import applicable_rules

DEFAULT_BUDGET = 6000
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate: one token per four characters, rounded up."""
    return -(-len(text) // CHARS_PER_TOKEN)


def build_context_pack(
    context: ContactContext,
    rules: Sequence[Rule],
    passages: Sequence[SearchHit],
    channel: MessageChannel,
    budget: int = DEFAULT_BUDGET,
) -> ContextPack:
    """Pack the facts, the applicable rules and as many passages as the budget allows.

    `rules` may hold any rule of the pack: only the approved ones that apply to this
    channel, segment and persona are kept. `passages` are best first.
    """
    applicable = applicable_rules(rules, channel, context.company.segment, context.contact.persona)
    used = _cost(context)
    truncated: list[str] = []
    if used > budget:
        truncated.append(f"facts alone use {used} estimated tokens, over the budget of {budget}")

    kept_rules, used = _take(applicable, used, budget, "rule", lambda r: r.id, truncated)
    kept_passages, used = _take(passages, used, budget, "passage", lambda p: p.chunk_id, truncated)
    return ContextPack(
        contact_context=context,
        rules=kept_rules,
        passages=kept_passages,
        estimated_tokens=used,
        truncated=tuple(truncated),
    )


def _cost(item: BaseModel) -> int:
    return estimate_tokens(item.model_dump_json())


def _take[T: BaseModel](
    items: Sequence[T],
    used: int,
    budget: int,
    kind: str,
    name: Callable[[T], str],
    truncated: list[str],
) -> tuple[tuple[T, ...], int]:
    """Keep the longest prefix of `items` that fits; record the ids of the rest."""
    kept: list[T] = []
    for index, item in enumerate(items):
        cost = _cost(item)
        if used + cost > budget:
            truncated.extend(f"{kind} {name(dropped)}" for dropped in items[index:])
            break
        kept.append(item)
        used += cost
    return tuple(kept), used
