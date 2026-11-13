"""The judge: a model that grades tone against the pack's rubric and checks each rule.

One structured call per email. The email is untrusted text, so it travels as the
`document`; the rubric and the rules are the pack's own and go in the instructions.
Before its scores count, the judge is calibrated: it grades emails a human already
scored, and it must land within one point of the human often enough, or the run fails
(`UncalibratedJudgeError`). If it does not, fix the rubric, never the labels.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from groundwork.core.domain.errors import UncalibratedJudgeError
from groundwork.core.domain.evals import Agreement, CalibrationCase, JudgeVerdict
from groundwork.core.domain.harmonize import HarmonizedEmail, MessageChannel
from groundwork.core.domain.knowhow import Rule, Usage
from groundwork.core.ports.model import ModelPort, Tier

TIER: Tier = "extraction"
RUBRIC_HEADING = "# Tone rubric of this client"


def judge_system(prompt: str, rubric: str) -> str:
    """The judge's instructions: the generic prompt, then the pack's tone rubric."""
    return f"{prompt.rstrip()}\n\n{RUBRIC_HEADING}\n{rubric.strip()}\n"


@dataclass(frozen=True)
class Judged:
    verdict: JudgeVerdict
    usage: Usage


def judge_email(
    model: ModelPort,
    system: str,
    email: HarmonizedEmail,
    channel: MessageChannel,
    segment: str,
    persona: str,
    rules: Sequence[Rule],
) -> Judged:
    """Grade one email: tone, and a verdict on each rule given."""
    listed = "\n".join(f"- {r.id} [{r.kind}]: {r.statement}" for r in rules) or "(none)"
    user = (
        f"Channel: {channel}. Contact segment: {segment}. Persona: {persona}.\n"
        f"Rules that apply to this email:\n{listed}\n\nGrade the email in the document."
    )
    answer = model.complete_structured(
        tier=TIER,
        system=system,
        user=user,
        schema=JudgeVerdict,
        document=f"Subject: {email.subject}\n\n{email.body}",
    )
    return Judged(verdict=answer.value, usage=answer.usage)


def calibrate(
    model: ModelPort, system: str, cases: Sequence[CalibrationCase]
) -> tuple[Agreement, Usage]:
    """Grade the human-scored emails and measure how often the judge is within one point."""
    usage = Usage()
    differences = []
    for case in cases:
        email = HarmonizedEmail(subject=case.subject, body=case.body, rationale="calibration")
        judged = judge_email(model, system, email, "external", "unspecified", "unspecified", ())
        differences.append(judged.verdict.tone - case.human_tone)
        usage = usage + judged.usage
    agree = sum(1 for d in differences if abs(d) <= 1)
    return Agreement(agree=agree, total=len(cases), differences=tuple(differences)), usage


def require_calibrated(agreement: Agreement, minimum: float) -> None:
    """Raise `UncalibratedJudgeError` unless the judge agrees with the humans often enough."""
    if agreement.total == 0:
        raise UncalibratedJudgeError(0.0, minimum, 0, 0)
    if agreement.rate < minimum:
        raise UncalibratedJudgeError(agreement.rate, minimum, agreement.agree, agreement.total)
