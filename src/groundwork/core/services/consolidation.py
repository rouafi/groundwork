"""Consolidate the rules of a pack across its interviews.

- Duplicates and conflicts are a judgment call: the extraction model proposes them by
  rule id, and code keeps only references to rules that exist. Duplicates are merged
  into one rule that keeps every provenance. Conflicts are flagged, never resolved:
  both rules stay proposed and a human decides.
- Coverage gaps are computed by code: audiences (segment, persona) that have CRM
  contacts but no rule addressing them specifically. A general rule applies to every
  audience, so it does not tell the team how to adapt to this one.
- Follow-up questions for the next interview are drafted by the cheap model.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from groundwork.core.domain.domain_pack import DomainPack
from groundwork.core.domain.knowhow import Conflict, CoverageGap, Rule, StageUsage
from groundwork.core.ports.crm import CrmPort
from groundwork.core.ports.model import ModelPort

MAX_QUESTIONS = 5


class _Group(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_ids: list[str]
    reason: str


class Consolidation(BaseModel):
    """Schema of the consolidation stage."""

    model_config = ConfigDict(extra="forbid")

    duplicates: list[_Group]
    conflicts: list[_Group]


class Questions(BaseModel):
    """Schema of the follow-up questions stage."""

    model_config = ConfigDict(extra="forbid")

    questions: list[str]


@dataclass(frozen=True)
class Consolidated:
    rules: tuple[Rule, ...]
    conflicts: tuple[Conflict, ...]
    usage: StageUsage | None


def consolidate(pack: str, rules: Sequence[Rule], model: ModelPort, system: str) -> Consolidated:
    """Merge duplicates, flag conflicts, and renumber the rules."""
    if len(rules) < 2:
        return Consolidated(rules=tuple(rules), conflicts=(), usage=None)
    answer = model.complete_structured(
        tier="extraction", system=system, user=_listing(rules), schema=Consolidation
    )
    known = {r.id for r in rules}
    groups = _valid_groups(answer.value.duplicates, known, exclusive=True)
    merged, merged_into = _merge(rules, groups)
    renumbered, new_id = _renumber(pack, merged)
    renamed = {i: new_id[merged_into.get(i, i)] for i in known}
    conflicts = _conflicts(pack, answer.value.conflicts, known, renamed)
    usage = StageUsage(stage="consolidate", calls=1, usage=answer.usage)
    return Consolidated(rules=renumbered, conflicts=conflicts, usage=usage)


def coverage_gaps(
    rules: Sequence[Rule], domain: DomainPack, crm: CrmPort
) -> tuple[CoverageGap, ...]:
    """Audiences with CRM contacts and no specific rule, most contacts first."""
    contacts = _contacts_by_audience(crm)
    specific = [r for r in rules if r.scope.segments or r.scope.personas]
    gaps = [
        CoverageGap(segment=segment, persona=persona, contacts=contacts.get((segment, persona), 0))
        for segment in domain.segments
        for persona in domain.personas
        if contacts.get((segment, persona))
        and not any(_addresses(r, segment, persona) for r in specific)
    ]
    return tuple(sorted(gaps, key=lambda g: -g.contacts))


def follow_up_questions(
    gaps: Sequence[CoverageGap], model: ModelPort, system: str
) -> tuple[tuple[str, ...], StageUsage | None]:
    """At most MAX_QUESTIONS questions for the next interview, on the largest gaps."""
    if not gaps:
        return (), None
    listing = "\n".join(
        f"- {g.segment} / {g.persona}: {g.contacts} contact(s)" for g in gaps[:MAX_QUESTIONS]
    )
    answer = model.complete_structured(
        tier="cheap", system=system, user=f"Audiences without rules:\n{listing}", schema=Questions
    )
    questions = tuple(q.strip() for q in answer.value.questions if q.strip())[:MAX_QUESTIONS]
    return questions, StageUsage(stage="questions", calls=1, usage=answer.usage)


def _listing(rules: Sequence[Rule]) -> str:
    return "\n".join(
        f"{r.id} [{r.kind}, channel={r.scope.channel}, segments={list(r.scope.segments)}, "
        f"personas={list(r.scope.personas)}, interview={r.provenance[0].interview_id}]: "
        f"{r.statement}"
        for r in rules
    )


def _valid_groups(groups: Sequence[_Group], known: set[str], *, exclusive: bool) -> list[_Group]:
    """Keep groups of at least two existing ids; with `exclusive`, an id joins one group only."""
    used: set[str] = set()
    valid = []
    for group in groups:
        ids = sorted({i for i in group.rule_ids if i in known} - (used if exclusive else set()))
        if len(ids) >= 2:
            valid.append(_Group(rule_ids=ids, reason=group.reason))
            used.update(ids)
    return valid


def _merge(rules: Sequence[Rule], groups: Sequence[_Group]) -> tuple[list[Rule], dict[str, str]]:
    merged_into = {i: g.rule_ids[0] for g in groups for i in g.rule_ids}
    by_id = {r.id: r for r in rules}
    merged = []
    for rule in rules:
        keeper = merged_into.get(rule.id, rule.id)
        if keeper != rule.id:
            continue
        members = [by_id[i] for i, k in merged_into.items() if k == keeper] or [rule]
        provenance = tuple(p for m in members for p in m.provenance)
        merged.append(rule.model_copy(update={"provenance": provenance}))
    return merged, merged_into


def _renumber(pack: str, rules: Sequence[Rule]) -> tuple[tuple[Rule, ...], dict[str, str]]:
    new_id = {r.id: f"{pack}-r-{n:03d}" for n, r in enumerate(rules, start=1)}
    return tuple(r.model_copy(update={"id": new_id[r.id]}) for r in rules), new_id


def _conflicts(
    pack: str, groups: Sequence[_Group], known: set[str], renamed: dict[str, str]
) -> tuple[Conflict, ...]:
    conflicts = []
    for group in _valid_groups(groups, known, exclusive=False):
        ids = sorted({renamed[i] for i in group.rule_ids})
        if len(ids) >= 2:
            reason = _rename_ids(pack, group.reason, renamed)
            conflicts.append(Conflict(rule_ids=tuple(ids), reason=reason))
    return tuple(conflicts)


def _rename_ids(pack: str, text: str, renamed: dict[str, str]) -> str:
    """Rewrite the rule ids the model wrote in a reason, full or short ('r-004'), so the
    reason names the rules a reviewer sees. Unknown ids are left as they are."""

    def rename(match: re.Match[str]) -> str:
        old = f"{pack}-{match.group('short')}"
        new = renamed.get(old)
        if new is None:
            return match.group(0)
        return new if match.group("pack") else new.removeprefix(f"{pack}-")

    pattern = rf"\b(?P<pack>{re.escape(pack)}-)?(?P<short>r-\d{{3}})\b"
    return re.sub(pattern, rename, text)


def _contacts_by_audience(crm: CrmPort) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for contact_id in crm.list_contact_ids():
        contact = crm.get_contact(contact_id)
        segment = crm.get_company(contact.company_id).segment
        key = (segment, contact.persona)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _addresses(rule: Rule, segment: str, persona: str) -> bool:
    return (not rule.scope.segments or segment in rule.scope.segments) and (
        not rule.scope.personas or persona in rule.scope.personas
    )
