from typing import Any

import pytest

from groundwork.core.domain.knowhow import Provenance, Rule, Scope
from groundwork.core.services.rules import applicable_rules

PROVENANCE = (Provenance(interview_id="acme-i-1", quote="q", start=0, end=1),)


def _rule(n: int, status: str = "approved", **scope: Any) -> Rule:
    return Rule(
        id=f"acme-r-{n:03d}",
        kind="practice",
        statement=f"Rule {n}.",
        scope=Scope(**scope),
        provenance=PROVENANCE,
        status=status,  # type: ignore[arg-type]
    )


# (scope of the rule, requested channel, segment, persona, applies?)
MATRIX = [
    ({}, "external", None, None, True),
    ({}, "internal", "smb", "end-user", True),
    ({"channel": "external"}, "external", None, None, True),
    ({"channel": "external"}, "internal", None, None, False),
    ({"channel": "internal"}, "internal", "smb", None, True),
    ({"segments": ("smb",)}, "external", "smb", None, True),
    ({"segments": ("smb",)}, "external", "enterprise", None, False),
    ({"segments": ("smb",)}, "external", None, None, False),
    ({"segments": ("smb", "mid-market")}, "internal", "mid-market", None, True),
    ({"personas": ("end-user",)}, "external", None, "end-user", True),
    ({"personas": ("end-user",)}, "external", None, "economic-buyer", False),
    ({"personas": ("end-user",)}, "external", "smb", None, False),
    ({"channel": "external", "segments": ("smb",), "personas": ("end-user",)},
     "external", "smb", "end-user", True),
    ({"channel": "external", "segments": ("smb",), "personas": ("end-user",)},
     "internal", "smb", "end-user", False),
    ({"channel": "external", "segments": ("smb",), "personas": ("end-user",)},
     "external", "enterprise", "end-user", False),
    ({"channel": "external", "segments": ("smb",), "personas": ("end-user",)},
     "external", "smb", "economic-buyer", False),
]  # fmt: skip


@pytest.mark.parametrize(("scope", "channel", "segment", "persona", "applies"), MATRIX)
def test_applicability_matrix(
    scope: dict[str, Any], channel: str, segment: str | None, persona: str | None, applies: bool
) -> None:
    rules = [_rule(1, **scope)]
    assert bool(applicable_rules(rules, channel, segment, persona)) is applies


def test_only_approved_rules_apply() -> None:
    rules = [_rule(1, status="proposed"), _rule(2)]
    assert [r.id for r in applicable_rules(rules, "external")] == ["acme-r-002"]


def test_most_specific_first_then_by_id() -> None:
    rules = [
        _rule(5),
        _rule(4, channel="external"),
        _rule(3, channel="external", segments=("smb",), personas=("end-user",)),
        _rule(2),
        _rule(1, segments=("smb",), personas=("end-user",)),
    ]
    ordered = applicable_rules(rules, "external", "smb", "end-user")
    assert [r.id for r in ordered] == [
        "acme-r-003",
        "acme-r-001",
        "acme-r-004",
        "acme-r-002",
        "acme-r-005",
    ]
