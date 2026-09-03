"""Small local quality evaluation that values recall over compression."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import BuildResult


@dataclass(slots=True)
class EvaluationMetrics:
    token_reduction: float
    critical_fact_recall: float
    constraint_recall: float
    relevant_file_recall: float
    irrelevant_file_rejection: float
    audit_pass_rate: float
    quality_score: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def evaluate_result(
    result: BuildResult,
    *,
    expected_relevant_files: list[str],
    expected_irrelevant_files: list[str],
) -> EvaluationMetrics:
    selected_files = {
        str(chunk.metadata["path"])
        for chunk in result.budget.selected
        if chunk.metadata.get("path")
    }
    relevant_recall = _recall(expected_relevant_files, selected_files)
    irrelevant_rejection = _rejection(expected_irrelevant_files, selected_files)
    constraint_recall = 1.0 if "hard_constraints" not in result.audit.missing_categories else 0.0
    critical_categories = {"task", "hard_constraints", "current_errors", "conflicts"}
    missing_critical = critical_categories & set(result.audit.missing_categories)
    critical_recall = 1.0 - len(missing_critical) / len(critical_categories)
    relevant_context_quality = (relevant_recall + irrelevant_rejection) / 2
    quality_score = critical_recall * constraint_recall * relevant_context_quality
    return EvaluationMetrics(
        token_reduction=result.statistics.reduction_percent / 100,
        critical_fact_recall=critical_recall,
        constraint_recall=constraint_recall,
        relevant_file_recall=relevant_recall,
        irrelevant_file_rejection=irrelevant_rejection,
        audit_pass_rate=1.0 if result.audit.passed else 0.0,
        quality_score=quality_score,
    )


def _recall(expected: list[str], selected: set[str]) -> float:
    if not expected:
        return 1.0
    return sum(path in selected for path in expected) / len(expected)


def _rejection(expected_irrelevant: list[str], selected: set[str]) -> float:
    if not expected_irrelevant:
        return 1.0
    return sum(path not in selected for path in expected_irrelevant) / len(expected_irrelevant)
