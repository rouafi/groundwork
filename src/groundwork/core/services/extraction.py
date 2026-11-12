"""Rule extraction: a code-driven workflow over ModelPort, not an agent (ADR 0007).

Per interview, in parallel and in sorted order:
1. ground: the extraction model writes statements, each cited from the transcript by the API;
2. type: the cheap model classifies them (kind, scope, products), by index;
3. filter: deterministic checks (grounding.check_candidate) keep or drop each one.
Then, per pack: ids are assigned in interview order, duplicates are merged and
conflicts flagged (consolidation), claims are checked against the CRM, and coverage
gaps get follow-up questions. A failing interview is reported and the others still
run. The workflow only ever proposes: approval is a human's commit.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from string import Template

from pydantic import BaseModel, ConfigDict

from groundwork.core.domain.domain_pack import DomainPack
from groundwork.core.domain.knowhow import (
    CoverageGap,
    Dropped,
    ExtractionReport,
    Failure,
    Interview,
    Rule,
    StageUsage,
    Usage,
)
from groundwork.core.ports.crm import CrmPort
from groundwork.core.ports.model import CitedStatement, ModelPort
from groundwork.core.services.consolidation import (
    Consolidated,
    consolidate,
    coverage_gaps,
    follow_up_questions,
)
from groundwork.core.services.grounding import TypedRule, check_candidate
from groundwork.core.services.rules_check import claim_contradictions

GROUND_INSTRUCTION = (
    "List the rules the expert states in this interview, "
    "one rule per situation, grouping the instructions that apply to the same situation."
)
STAGES = ("ground", "type", "consolidate", "questions")


@dataclass(frozen=True)
class ExtractionPrompts:
    """System prompts of the workflow, as `string.Template` text using the domain vocabulary."""

    ground: str
    type: str
    consolidate: str
    questions: str


PROMPT_NAMES = {
    "ground": "ground_rules",
    "type": "type_rules",
    "consolidate": "consolidate_rules",
    "questions": "gap_questions",
}


class TypedRules(BaseModel):
    """Schema of the typing stage: one item per cited statement."""

    model_config = ConfigDict(extra="forbid")

    rules: list[TypedRule]


@dataclass(frozen=True)
class Extraction:
    """What extracting one interview produced."""

    rules: tuple[Rule, ...] = ()
    dropped: tuple[Dropped, ...] = ()
    usage: Mapping[str, StageUsage] = field(default_factory=dict)


@dataclass(frozen=True)
class Workflow:
    """Everything the stages need, fixed for one run."""

    pack: str
    domain: DomainPack
    crm: CrmPort
    model: ModelPort
    prompts: ExtractionPrompts


def render(template: str, domain: DomainPack) -> str:
    """Fill a prompt template with the domain vocabulary."""
    return Template(template).substitute(
        segments=", ".join(domain.segments),
        personas=", ".join(domain.personas),
        channels=", ".join(domain.channels),
        default_tone=domain.defaults.tone,
    )


def extract_rules(
    workflow: Workflow, interviews: Sequence[Interview], max_concurrency: int = 4
) -> ExtractionReport:
    """Run the workflow on every interview of a pack and assemble the report."""
    ordered = sorted(interviews, key=lambda i: i.id)
    with ThreadPoolExecutor(max_workers=max(1, max_concurrency)) as pool:
        outcomes = list(pool.map(_isolated(lambda i: extract_interview(workflow, i)), ordered))
    extractions = [o for o in outcomes if isinstance(o, Extraction)]
    numbered = number_rules(workflow.pack, [r for e in extractions for r in e.rules])
    consolidated, failures = _consolidate(workflow, numbered)
    gaps = coverage_gaps(consolidated.rules, workflow.domain, workflow.crm)
    questions, questions_usage, question_failures = _questions(workflow, gaps, consolidated.rules)
    pack_usage = {u.stage: u for u in (consolidated.usage, questions_usage) if u is not None}
    return ExtractionReport(
        pack=workflow.pack,
        rules=consolidated.rules,
        dropped=tuple(d for e in extractions for d in e.dropped),
        conflicts=consolidated.conflicts,
        contradictions=claim_contradictions(consolidated.rules, workflow.crm),
        gaps=gaps,
        questions=questions,
        failures=(
            *(o for o in outcomes if isinstance(o, Failure)),
            *failures,
            *question_failures,
        ),
        usage=sum_usage([*(e.usage for e in extractions), pack_usage]),
    )


def _consolidate(
    workflow: Workflow, rules: Sequence[Rule]
) -> tuple[Consolidated, tuple[Failure, ...]]:
    """Consolidate the pack; on failure keep the rules as they are and report it."""
    system = render(workflow.prompts.consolidate, workflow.domain)
    try:
        return consolidate(workflow.pack, rules, workflow.model, system), ()
    except Exception as exc:  # reported in the report and by the CLI exit code
        unchanged = Consolidated(rules=tuple(rules), conflicts=(), usage=None)
        return unchanged, (Failure(where="consolidate", error=_describe(exc)),)


def _questions(
    workflow: Workflow, gaps: Sequence[CoverageGap], rules: Sequence[Rule]
) -> tuple[tuple[str, ...], StageUsage | None, tuple[Failure, ...]]:
    """Follow-up questions, only when rules exist to compare the gaps with."""
    if not rules:
        return (), None, ()
    system = render(workflow.prompts.questions, workflow.domain)
    try:
        questions, usage = follow_up_questions(gaps, workflow.model, system)
    except Exception as exc:  # reported in the report and by the CLI exit code
        return (), None, (Failure(where="questions", error=_describe(exc)),)
    return questions, usage, ()


def extract_interview(workflow: Workflow, interview: Interview) -> Extraction:
    """Ground, type and filter the rules of one interview."""
    grounded = workflow.model.cite(
        tier="extraction",
        system=render(workflow.prompts.ground, workflow.domain),
        instruction=GROUND_INSTRUCTION,
        document=interview.text,
    )
    statements = grounded.value
    if not statements:
        return Extraction(
            usage={"ground": StageUsage(stage="ground", calls=1, usage=grounded.usage)}
        )
    typed = workflow.model.complete_structured(
        tier="cheap",
        system=render(workflow.prompts.type, workflow.domain),
        user=_typing_request(workflow.crm, statements),
        schema=TypedRules,
    )
    rules, dropped = _filter(workflow, interview, statements, typed.value.rules)
    return Extraction(
        rules=rules,
        dropped=dropped,
        usage={
            "ground": StageUsage(stage="ground", calls=1, usage=grounded.usage),
            "type": StageUsage(stage="type", calls=1, usage=typed.usage),
        },
    )


def number_rules(pack: str, rules: Sequence[Rule]) -> tuple[Rule, ...]:
    """Ids `<pack>-r-<nnn>`: interview order (input order), then position in the transcript."""
    interview_rank = {r.provenance[0].interview_id: None for r in rules}
    rank = {interview_id: n for n, interview_id in enumerate(interview_rank)}
    ordered = sorted(
        rules, key=lambda r: (rank[r.provenance[0].interview_id], r.provenance[0].start)
    )
    return tuple(
        r.model_copy(update={"id": f"{pack}-r-{n:03d}"}) for n, r in enumerate(ordered, start=1)
    )


def sum_usage(per_interview: Iterable[Mapping[str, StageUsage]]) -> tuple[StageUsage, ...]:
    """Total calls and tokens per stage, in stage order."""
    totals: dict[str, StageUsage] = {}
    for usage in per_interview:
        for stage, item in usage.items():
            prev = totals.get(stage, StageUsage(stage=stage, calls=0, usage=Usage()))
            totals[stage] = StageUsage(
                stage=stage, calls=prev.calls + item.calls, usage=prev.usage + item.usage
            )
    return tuple(totals[s] for s in sorted(totals, key=_stage_rank))


def _stage_rank(stage: str) -> tuple[int, str]:
    return (STAGES.index(stage) if stage in STAGES else len(STAGES), stage)


def _filter(
    workflow: Workflow,
    interview: Interview,
    statements: Sequence[CitedStatement],
    typed: Sequence[TypedRule],
) -> tuple[tuple[Rule, ...], tuple[Dropped, ...]]:
    product_ids = set(workflow.crm.list_product_ids())
    by_index = {t.index: t for t in typed}
    rules: list[Rule] = []
    dropped: list[Dropped] = []
    for index, statement in enumerate(statements):
        item = by_index.get(index)
        if item is None:
            dropped.append(
                Dropped(interview_id=interview.id, statement=statement.text, reason="not typed")
            )
            continue
        result = check_candidate(interview, statement, item, workflow.domain, product_ids)
        if isinstance(result, Rule):
            rules.append(result)
        else:
            dropped.append(result)
    return tuple(rules), tuple(dropped)


def _typing_request(crm: CrmPort, statements: Sequence[CitedStatement]) -> str:
    products = crm.get_products(crm.list_product_ids())
    catalog = "\n".join(f"- {p.id}: {p.name}" for p in products)
    listed = "\n".join(
        f"{n}. {s.text} (quote: {' / '.join(q.text.strip() for q in s.quotes) or 'none'})"
        for n, s in enumerate(statements)
    )
    return f"Product catalog:\n{catalog}\n\nRules:\n{listed}"


def _isolated(
    step: Callable[[Interview], Extraction],
) -> Callable[[Interview], Extraction | Failure]:
    """Run one interview; turn any error into a reported failure so the others continue."""

    def run(interview: Interview) -> Extraction | Failure:
        try:
            return step(interview)
        except Exception as exc:  # reported in the report and by the CLI exit code
            return Failure(where=interview.id, error=_describe(exc))

    return run


def _describe(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"
