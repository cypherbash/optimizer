"""Correctness-first token budgeting."""

from __future__ import annotations

from dataclasses import replace

from .models import BudgetResult, ContextChunk
from .tokenizer import TokenCounter

CATEGORY_SHARES = {
    "constraint": 0.14,
    "decision": 0.10,
    "project_state": 0.08,
    "current_behavior": 0.06,
    "desired_behavior": 0.06,
    "error": 0.08,
    "source_code": 0.28,
    "test": 0.12,
    "conversation": 0.06,
    "repository_structure": 0.02,
}

MANDATORY_PRIORITY = {
    "task": 0,
    "constraint": 1,
    "conflict": 2,
    "error": 3,
    "decision": 4,
}


def apply_budget(
    chunks: list[ContextChunk],
    budget: int,
    counter: TokenCounter,
    *,
    hard_budget: bool = False,
    minimum_score: float = 0.04,
) -> BudgetResult:
    if budget <= 0:
        raise ValueError("Budget must be greater than zero")

    mandatory = sorted(
        (chunk for chunk in chunks if chunk.mandatory),
        key=lambda chunk: (MANDATORY_PRIORITY.get(chunk.kind, 20), -chunk.score, chunk.id),
    )
    optional = [chunk for chunk in chunks if not chunk.mandatory]
    mandatory_tokens = sum(chunk.token_count for chunk in mandatory)
    warnings: list[str] = []

    if mandatory_tokens > budget and not hard_budget:
        warnings.append(
            f"Requested budget: {budget} tokens; mandatory context: {mandatory_tokens} tokens. "
            "The result exceeds the budget to preserve critical information."
        )
        return BudgetResult(
            selected=mandatory,
            dropped=optional,
            requested_budget=budget,
            mandatory_tokens=mandatory_tokens,
            selected_tokens=mandatory_tokens,
            warnings=warnings,
        )

    if mandatory_tokens > budget and hard_budget:
        selected, dropped = _fit_mandatory_hard(mandatory, optional, budget, counter, warnings)
        return BudgetResult(
            selected=selected,
            dropped=dropped,
            requested_budget=budget,
            mandatory_tokens=mandatory_tokens,
            selected_tokens=sum(chunk.token_count for chunk in selected),
            warnings=warnings,
        )

    selected = list(mandatory)
    selected_ids = {chunk.id for chunk in selected}
    used = mandatory_tokens
    category_used: dict[str, int] = {}
    targets = {kind: int(budget * share) for kind, share in CATEGORY_SHARES.items()}

    useful = [chunk for chunk in optional if chunk.score >= minimum_score]
    ordered = sorted(
        useful,
        key=lambda chunk: (
            -(chunk.score / max(1.0, chunk.token_count**0.35)),
            -chunk.score,
            chunk.id,
        ),
    )

    # First pass preserves useful category diversity; the second redistributes unused space.
    for enforce_targets in (True, False):
        for chunk in ordered:
            if chunk.id in selected_ids or used + chunk.token_count > budget:
                continue
            target = targets.get(chunk.kind, budget)
            if enforce_targets and category_used.get(chunk.kind, 0) + chunk.token_count > target:
                continue
            selected.append(chunk)
            selected_ids.add(chunk.id)
            used += chunk.token_count
            category_used[chunk.kind] = category_used.get(chunk.kind, 0) + chunk.token_count

    dropped = [chunk for chunk in chunks if chunk.id not in selected_ids]
    return BudgetResult(
        selected=selected,
        dropped=dropped,
        requested_budget=budget,
        mandatory_tokens=mandatory_tokens,
        selected_tokens=used,
        warnings=warnings,
    )


def _fit_mandatory_hard(
    mandatory: list[ContextChunk],
    optional: list[ContextChunk],
    budget: int,
    counter: TokenCounter,
    warnings: list[str],
) -> tuple[list[ContextChunk], list[ContextChunk]]:
    warnings.append(
        "Hard-budget mode was requested: mandatory context had to be truncated or omitted. "
        "The result may be insufficient for correct reasoning."
    )
    selected: list[ContextChunk] = []
    dropped: list[ContextChunk] = list(optional)
    used = 0
    for chunk in mandatory:
        remaining = budget - used
        if remaining <= 0:
            dropped.append(chunk)
            continue
        if chunk.token_count <= remaining:
            selected.append(chunk)
            used += chunk.token_count
            continue
        truncated_text = _truncate_to_tokens(chunk.text, remaining, counter)
        if truncated_text:
            truncated = replace(
                chunk,
                id=f"{chunk.id}:truncated",
                text=truncated_text + "\n[TRUNCATED BY --hard-budget]",
                token_count=counter.count(truncated_text + "\n[TRUNCATED BY --hard-budget]"),
                reasons=[*chunk.reasons, "truncated only because --hard-budget was explicit"],
            )
            selected.append(truncated)
        dropped.append(chunk)
        break
    return selected, dropped


def _truncate_to_tokens(text: str, budget: int, counter: TokenCounter) -> str:
    if budget <= 0:
        return ""
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if counter.count(text[:middle]) <= max(0, budget - 8):
            low = middle
        else:
            high = middle - 1
    return text[:low].rstrip()
