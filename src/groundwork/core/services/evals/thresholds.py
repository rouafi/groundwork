"""Turn a pack's measured metrics into a verdict against its thresholds."""

from groundwork.core.domain.evals import PackMetrics, ThresholdResult, Thresholds


def check_thresholds(thresholds: Thresholds, metrics: PackMetrics) -> tuple[ThresholdResult, ...]:
    """One result per scorer, in a fixed order. A scorer that was not measured is skipped."""
    return (
        _at_most("fact_false_claims", metrics.fact_false_claims, thresholds.fact_false_claims),
        _at_most("rule_violations", metrics.rule_violations, thresholds.rule_violations),
        _at_least("tone_mean", metrics.tone_mean, thresholds.tone_mean_min, "tone_mean_min"),
        _at_least(
            "routing_accuracy",
            metrics.routing_accuracy,
            thresholds.routing_accuracy_min,
            "routing_accuracy_min",
        ),
        _at_least(
            "traceability", metrics.traceability, thresholds.traceability_min, "traceability_min"
        ),
        _at_least(
            "retrieval_recall_at_5",
            metrics.retrieval_recall_at_5,
            thresholds.retrieval_recall_at_5_min,
            "retrieval_recall_at_5_min",
        ),
        _at_least(
            "judge_agreement",
            metrics.judge_agreement,
            thresholds.judge_agreement_min,
            "judge_agreement_min",
        ),
    )


def _at_most(scorer: str, value: float, limit: float) -> ThresholdResult:
    passed = value <= limit
    message = (
        f"{scorer} {value:g} is within {limit:g}"
        if passed
        else (f"{scorer} {value:g} is above the limit {limit:g}")
    )
    return ThresholdResult(
        scorer=scorer, value=value, threshold=limit, passed=passed, message=message
    )


def _at_least(scorer: str, value: float | None, minimum: float, name: str) -> ThresholdResult:
    if value is None:
        message = f"{scorer} was not measured: skipped"
        return ThresholdResult(
            scorer=scorer, value=None, threshold=minimum, passed=True, message=message
        )
    passed = value >= minimum
    message = (
        f"{scorer} {value:.2f} meets {name} {minimum:.2f}"
        if passed
        else f"{scorer} {value:.2f} is below {name} {minimum:.2f}"
    )
    return ThresholdResult(
        scorer=scorer, value=value, threshold=minimum, passed=passed, message=message
    )
