"""Which approved rules apply to a message, and in which order to read them."""

from collections.abc import Iterable

from groundwork.core.domain.knowhow import Rule


def applicable_rules(
    rules: Iterable[Rule],
    channel: str,
    segment: str | None = None,
    persona: str | None = None,
) -> tuple[Rule, ...]:
    """Approved rules whose scope covers the message, most specific first, then by id.

    A rule applies when its channel is `any` or `channel`, and its segments and
    personas are empty or contain the requested value. Proposed rules never apply.
    """
    matching = (
        r for r in rules if r.status == "approved" and r.scope.applies_to(channel, segment, persona)
    )
    return tuple(sorted(matching, key=lambda r: (-r.scope.specificity, r.id)))
