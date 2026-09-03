"""Orchestrate extraction, analysis, ranking, budgeting, rendering, and audit."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .audit import audit_context
from .budget import apply_budget
from .models import BuildResult, BuildStatistics, ContextChunk
from .relevance import build_candidates, rank_chunks
from .repo_analyzer import analyze_repository
from .state_extractor import SemanticExtractor, extract_state
from .tokenizer import TokenCounter, get_token_counter


@dataclass(slots=True)
class BuildOptions:
    budget: int = 8_000
    recent_messages: int = 6
    context_lines: int = 15
    dependency_depth: int = 2
    hard_budget: bool = False
    tokenizer: str = "auto"
    model: str = "gpt-4o-mini"


def build_context(
    task: str,
    conversation: str = "",
    repository: Path | None = None,
    *,
    options: BuildOptions | None = None,
    counter: TokenCounter | None = None,
    semantic_extractor: SemanticExtractor | None = None,
) -> BuildResult:
    config = options or BuildOptions()
    token_counter = counter or get_token_counter(config.tokenizer, config.model)
    state = extract_state(task, conversation, semantic_extractor)
    analysis = analyze_repository(repository) if repository is not None else None
    candidates = build_candidates(
        task,
        conversation,
        state,
        analysis,
        token_counter,
        recent_message_count=config.recent_messages,
        context_lines=config.context_lines,
    )
    ranked = rank_chunks(
        candidates,
        task,
        state,
        analysis,
        dependency_depth=config.dependency_depth,
    )
    budget_result = apply_budget(
        ranked,
        config.budget,
        token_counter,
        hard_budget=config.hard_budget,
    )
    rendered = render_context(budget_result.selected)
    rendered_tokens = token_counter.count(rendered)
    if rendered_tokens > config.budget and budget_result.mandatory_tokens <= config.budget:
        budget_result.warnings.append(
            f"Rendered headings add overhead: output is {rendered_tokens} tokens for a "
            f"{config.budget}-token budget. Reduce the requested content budget if strict output "
            "size is required."
        )
    audit = audit_context(state, rendered)

    selected_by_kind: dict[str, int] = defaultdict(int)
    for chunk in budget_result.selected:
        selected_by_kind[chunk.kind] += chunk.token_count
    repository_tokens = sum(
        chunk.token_count
        for chunk in candidates
        if chunk.kind in {"source_code", "test", "repository_structure"}
    )
    total_candidate_tokens = sum(chunk.token_count for chunk in candidates)
    original_tokens = (
        token_counter.count(task) + token_counter.count(conversation) + repository_tokens
    )
    reduction = max(0.0, (1 - rendered_tokens / original_tokens) * 100) if original_tokens else 0.0
    statistics = BuildStatistics(
        original_conversation_tokens=token_counter.count(conversation),
        repository_candidate_tokens=repository_tokens,
        total_candidate_tokens=total_candidate_tokens,
        selected_by_kind=dict(sorted(selected_by_kind.items())),
        optimized_tokens=rendered_tokens,
        requested_budget=config.budget,
        reduction_percent=reduction,
        audit_passed=audit.passed,
    )
    return BuildResult(rendered, state, budget_result, audit, statistics)


SECTION_ORDER = [
    ("task", "TASK"),
    ("constraint", "HARD AND SOFT CONSTRAINTS"),
    ("conflict", "CONFLICTS TO RESOLVE"),
    ("project_state", "RELEVANT PROJECT STATE"),
    ("current_behavior", "CURRENT BEHAVIOR"),
    ("desired_behavior", "DESIRED BEHAVIOR"),
    ("decision", "DECISIONS ALREADY MADE"),
    ("rejected_approach", "REJECTED APPROACHES"),
    ("error", "CURRENT ERRORS"),
    ("open_question", "OPEN QUESTIONS"),
    ("repository_structure", "REPOSITORY STRUCTURE"),
    ("source_code", "RELEVANT CODE"),
    ("test", "RELEVANT TESTS"),
    ("conversation", "RECENT CONVERSATION"),
    ("assumption", "ASSUMPTIONS"),
]


def render_context(chunks: list[ContextChunk]) -> str:
    grouped: dict[str, list[ContextChunk]] = defaultdict(list)
    for chunk in chunks:
        grouped[chunk.kind].append(chunk)

    output: list[str] = []
    for kind, title in SECTION_ORDER:
        selected = grouped.get(kind, [])
        if not selected:
            continue
        output.append(f"# {title}\n")
        ordering = (
            (lambda item: (item.metadata.get("sequence", 0), item.id))
            if kind == "conversation"
            else (lambda item: (-item.score, item.source, item.id))
        )
        for chunk in sorted(selected, key=ordering):
            if kind in {"source_code", "test"}:
                start = chunk.metadata.get("line_start")
                end = chunk.metadata.get("line_end")
                location = f":{start}-{end}" if start and end else ""
                language = chunk.metadata.get("language", "text")
                output.append(f"## {chunk.source}{location}\n\n```{language}\n{chunk.text}\n```\n")
            elif kind == "repository_structure":
                output.append(f"```text\n{chunk.text}\n```\n")
            elif kind in {"task", "conversation"}:
                output.append(f"{chunk.text}\n")
            else:
                output.append(f"- {chunk.text}\n")
    return "\n".join(output).rstrip() + "\n"


def format_explanations(result: BuildResult, *, include_dropped: bool = True) -> str:
    lines = ["SELECTED"]
    for chunk in sorted(result.budget.selected, key=lambda item: (-item.score, item.id)):
        lines.extend(_explanation_lines(chunk, "Selected"))
    if include_dropped:
        lines.append("\nDROPPED")
        for chunk in sorted(result.budget.dropped, key=lambda item: (-item.score, item.id)):
            lines.extend(_explanation_lines(chunk, "Dropped"))
    return "\n".join(lines).rstrip() + "\n"


def _explanation_lines(chunk: ContextChunk, disposition: str) -> list[str]:
    location = chunk.source
    if chunk.metadata.get("line_start"):
        location += f":{chunk.metadata['line_start']}-{chunk.metadata['line_end']}"
    reasons = [f"- {reason}" for reason in chunk.reasons]
    if disposition == "Dropped" and chunk.score < 0.04:
        reasons.append("- below the minimum relevance threshold")
    elif disposition == "Dropped":
        reasons.append("- did not fit after higher-value context")
    return [f"\n{location}\nscore: {chunk.score:.3f}; tokens: {chunk.token_count}", *reasons]
