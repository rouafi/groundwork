"""The policy engine: pure code that decides what happens to an email. No model.

`decide` routes an email once its claims are checked. The rules, in order:
- a claim the facts contradict (`false`) blocks;
- a forbidden pattern of the channel blocks;
- an external email never auto-sends: a valid one goes to a human;
- an unknown claim goes to a human, on any channel (ADR 0008);
- an internal email auto-sends only when nothing above fired and the policy allows it.

None of this is configurable. `merge_policies` can only add patterns, lower limits and
turn internal auto-send off.
"""

import re
from collections.abc import Sequence

from groundwork.core.domain.claims import ClaimCheck
from groundwork.core.domain.harmonize import Decision, HarmonizedEmail, MessageChannel
from groundwork.core.domain.policy import ForbiddenPatterns, Policies, PolicyOverrides

SNIPPET_CHARS = 60


def merge_policies(domain: Policies, client: PolicyOverrides | None = None) -> Policies:
    """Core ceilings, then the domain defaults, then the client overrides, never relaxing.

    Patterns accumulate (domain first, then client, duplicates dropped). Limits only go
    down. Internal auto-send stays on only if the domain and the client both leave it on.
    """
    if client is None:
        return domain
    return Policies(
        forbidden_patterns=ForbiddenPatterns(
            internal=_union(domain.forbidden_patterns.internal, client.forbidden_patterns.internal),
            external=_union(domain.forbidden_patterns.external, client.forbidden_patterns.external),
        ),
        limits=domain.limits.lowered_by(client.limits),
        auto_send_internal=domain.auto_send_internal and client.auto_send_internal is not False,
    )


def decide(
    email: HarmonizedEmail,
    claim_checks: Sequence[ClaimCheck],
    channel: MessageChannel,
    policies: Policies,
) -> Decision:
    """Route an email: `blocked`, `approval` or `auto_send`, with every reason that applies."""
    blocking = [
        f"false claim: {c.claim!r} ({c.reason})" for c in claim_checks if c.status == "false"
    ]
    blocking += _pattern_hits(email, channel, policies)
    if blocking:
        return Decision(route="blocked", reasons=tuple(blocking))

    unknown = [c for c in claim_checks if c.status == "unknown"]
    if channel == "external":
        reasons = ["external emails are never sent automatically: a human approves them"]
        return Decision(route="approval", reasons=(*reasons, *_unknown_reasons(unknown)))
    if unknown:
        return Decision(route="approval", reasons=_unknown_reasons(unknown))
    if not policies.auto_send_internal:
        return Decision(route="approval", reasons=("auto-send is off for internal emails",))
    return Decision(
        route="auto_send", reasons=("internal email: no false claim, no forbidden pattern",)
    )


def _unknown_reasons(unknown: Sequence[ClaimCheck]) -> tuple[str, ...]:
    return tuple(f"unknown claim needs a human: {c.claim!r} ({c.reason})" for c in unknown)


def _pattern_hits(email: HarmonizedEmail, channel: MessageChannel, policies: Policies) -> list[str]:
    patterns = getattr(policies.forbidden_patterns, channel)
    text = f"{email.subject}\n{email.body}"
    hits = []
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            snippet = match.group(0)[:SNIPPET_CHARS]
            hits.append(f"forbidden pattern {pattern!r} matched {snippet!r} ({channel} email)")
    return hits


def _union(first: Sequence[str], second: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys([*first, *second]))
