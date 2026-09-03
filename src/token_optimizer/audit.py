"""Deterministic loss audit and optional semantic audit boundary."""

from __future__ import annotations

import re
from typing import Protocol

from .models import AuditResult, ContextState, EvidenceItem


class ContextAuditor(Protocol):
    def audit(self, original_state: ContextState, optimized_context: str) -> AuditResult:
        """Compare structured source state with the optimized context."""


def audit_context(state: ContextState, optimized_context: str) -> AuditResult:
    normalized_context = _normalize(optimized_context)
    missing: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if state.goal and _normalize(state.goal) not in normalized_context:
        missing.append("task")
        recommendations.append("Restore the original user task verbatim.")

    _require_items(
        state.hard_constraints,
        normalized_context,
        "hard_constraints",
        missing,
        recommendations,
    )
    _require_items(
        state.current_errors,
        normalized_context,
        "current_errors",
        missing,
        recommendations,
    )
    _require_items(state.conflicts, normalized_context, "conflicts", missing, recommendations)

    for category, items in {
        "decisions": state.decisions,
        "current_behavior": state.current_behavior,
        "desired_behavior": state.desired_behavior,
    }.items():
        absent = [item.text for item in items if _normalize(item.text) not in normalized_context]
        if absent:
            warnings.append(f"{category}: {len(absent)} extracted item(s) were not selected")

    identifiers = [
        item.text
        for item in state.important_identifiers
        if _normalize(item.text) not in normalized_context
    ]
    if identifiers:
        warnings.append(f"Important identifiers not present: {', '.join(identifiers[:8])}")

    if not re.search(r"(?im)^#\s+RELEVANT (?:CODE|TESTS)", optimized_context):
        warnings.append("No source or test context was selected.")

    return AuditResult(
        passed=not missing,
        missing_categories=sorted(set(missing)),
        warnings=warnings,
        recommendations=recommendations,
    )


def _require_items(
    items: list[EvidenceItem],
    context: str,
    category: str,
    missing: list[str],
    recommendations: list[str],
) -> None:
    absent = [item.text for item in items if _normalize(item.text) not in context]
    if absent:
        missing.append(category)
        recommendations.append(f"Restore {len(absent)} missing item(s) from {category}.")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()
