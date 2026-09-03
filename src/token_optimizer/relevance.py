"""Candidate generation and explainable local relevance scoring."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque

from .chunking import fixed_source_ranges, recent_messages, source_range
from .models import ContextChunk, ContextState, RepositoryAnalysis
from .tokenizer import TokenCounter

WORD_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
STOP_WORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "but",
    "change",
    "code",
    "context",
    "file",
    "for",
    "from",
    "have",
    "implement",
    "into",
    "must",
    "not",
    "should",
    "that",
    "the",
    "this",
    "use",
    "with",
}


def task_terms(task: str, state: ContextState) -> set[str]:
    material = [task]
    material.extend(item.text for item in state.important_identifiers)
    material.extend(item.text for item in state.relevant_files)
    terms = {term.casefold() for term in WORD_PATTERN.findall("\n".join(material))}
    return {term for term in terms if len(term) >= 3 and term not in STOP_WORDS}


def build_candidates(
    task: str,
    conversation: str,
    state: ContextState,
    analysis: RepositoryAnalysis | None,
    counter: TokenCounter,
    *,
    recent_message_count: int = 6,
    context_lines: int = 15,
) -> list[ContextChunk]:
    chunks: list[ContextChunk] = []
    if task.strip():
        chunks.append(_chunk("task", task.strip(), "task", counter, mandatory=True))

    _state_chunks(chunks, state, counter)
    for index, message in enumerate(recent_messages(conversation, recent_message_count)):
        chunk = _chunk("conversation", message, f"conversation:recent:{index + 1}", counter)
        chunk.recency_score = (index + 1) / max(1, recent_message_count)
        chunk.metadata["sequence"] = index
        chunk.reasons.append("one of the latest raw conversation messages")
        chunks.append(chunk)

    if analysis is not None:
        tree_text = "\n".join(analysis.tree)
        chunks.append(_chunk("repository_structure", tree_text, "repository tree", counter))
        _repository_chunks(chunks, analysis, counter, context_lines)
        if analysis.git_diff:
            diff_chunk = _chunk("source_code", analysis.git_diff, "git diff", counter)
            diff_chunk.metadata["changed"] = True
            diff_chunk.reasons.append("current unstaged git diff")
            chunks.append(diff_chunk)
        if analysis.git_diff_cached:
            diff_chunk = _chunk(
                "source_code", analysis.git_diff_cached, "git diff --cached", counter
            )
            diff_chunk.metadata["changed"] = True
            diff_chunk.reasons.append("current staged git diff")
            chunks.append(diff_chunk)
    return chunks


def rank_chunks(
    chunks: list[ContextChunk],
    task: str,
    state: ContextState,
    analysis: RepositoryAnalysis | None,
    *,
    dependency_depth: int = 2,
) -> list[ContextChunk]:
    terms = task_terms(task, state)
    dependency_distances = _dependency_distances(analysis, terms, dependency_depth)
    identifiers = {item.text.casefold() for item in state.important_identifiers}

    for chunk in chunks:
        chunk_terms = {term.casefold() for term in WORD_PATTERN.findall(chunk.text)}
        overlap = terms & chunk_terms
        chunk.relevance_score = min(1.0, len(overlap) / max(1, min(8, len(terms))))
        if overlap:
            chunk.reasons.append(f"matches task terms: {', '.join(sorted(overlap)[:6])}")

        symbol = str(chunk.metadata.get("symbol", "")).casefold()
        symbol_short = symbol.rsplit(".", 1)[-1]
        structural = 0.0
        if symbol and (symbol in identifiers or symbol_short in terms):
            structural = 1.0
            chunk.reasons.append(f"defines task-referenced symbol {chunk.metadata['symbol']}")
        elif chunk.metadata.get("path") and any(
            term in str(chunk.metadata["path"]).casefold() for term in terms
        ):
            structural = 0.55
            chunk.reasons.append("filename matches task terminology")

        distance = dependency_distances.get(symbol) or dependency_distances.get(symbol_short)
        if distance is not None:
            chunk.dependency_score = 1.0 / max(1, distance)
            if distance > 1:
                chunk.reasons.append(f"dependency at depth {distance - 1} from a relevant symbol")
        if chunk.metadata.get("is_test") and (overlap or structural > 0):
            structural = max(structural, 0.85)
            chunk.reasons.append("test covers task-relevant terminology")
        if chunk.metadata.get("changed"):
            structural = min(1.0, structural + 0.3)
            chunk.reasons.append("file is modified in the current git worktree")
        chunk.dependency_score = max(chunk.dependency_score, structural)

        if chunk.kind in {"constraint", "decision", "error"}:
            chunk.decision_score = 1.0 if chunk.kind != "decision" else 0.85
        if chunk.kind == "task":
            chunk.relevance_score = 1.0
            chunk.decision_score = 1.0

        chunk.score = (
            chunk.relevance_score * 0.50
            + chunk.dependency_score * 0.25
            + chunk.decision_score * 0.15
            + chunk.recency_score * 0.10
        )
        if chunk.mandatory:
            chunk.score = max(chunk.score, 1.0)
        if chunk.kind == "decision" and (overlap or chunk.source == "task"):
            chunk.mandatory = True
            chunk.score = max(chunk.score, 0.95)
            chunk.reasons.append("task-relevant recorded decision")
        if not chunk.reasons:
            chunk.reasons.append("no direct task or dependency signal")

    return sorted(chunks, key=lambda item: (-item.score, item.token_count, item.id))


def _state_chunks(chunks: list[ContextChunk], state: ContextState, counter: TokenCounter) -> None:
    mapping = {
        "hard_constraints": ("constraint", True),
        "soft_constraints": ("constraint", False),
        "relevant_facts": ("project_state", False),
        "decisions": ("decision", False),
        "open_questions": ("open_question", False),
        "current_errors": ("error", True),
        "current_behavior": ("current_behavior", False),
        "desired_behavior": ("desired_behavior", False),
        "assumptions": ("assumption", False),
        "conflicts": ("conflict", True),
    }
    for field_name, (kind, always_mandatory) in mapping.items():
        for item in getattr(state, field_name):
            mandatory = always_mandatory or item.importance.value == "critical"
            chunks.append(
                _chunk(
                    kind, item.text, item.provenance or item.source, counter, mandatory=mandatory
                )
            )
    for rejected in state.rejected_approaches:
        text = f"{rejected.approach}\nReason: {rejected.reason}"
        chunks.append(_chunk("rejected_approach", text, rejected.source, counter))


def _repository_chunks(
    chunks: list[ContextChunk],
    analysis: RepositoryAnalysis,
    counter: TokenCounter,
    context_lines: int,
) -> None:
    for relative, info in analysis.files.items():
        path = analysis.root / relative
        emitted = False
        for symbol in info.symbols:
            # Methods and functions are the useful edit unit. Class ranges would duplicate methods.
            if symbol.kind == "class" and any(
                child.qualified_name.startswith(f"{symbol.qualified_name}.")
                for child in info.symbols
            ):
                continue
            text, start, end = source_range(
                path, symbol.line_start, symbol.line_end, context_lines=context_lines
            )
            chunk = _chunk("test" if info.is_test else "source_code", text, relative, counter)
            chunk.metadata.update(
                {
                    "path": relative,
                    "line_start": start,
                    "line_end": end,
                    "symbol": symbol.qualified_name,
                    "calls": symbol.calls,
                    "is_test": info.is_test,
                    "changed": info.changed,
                    "language": info.language,
                }
            )
            chunks.append(chunk)
            emitted = True
        if not emitted:
            for text, start, end in fixed_source_ranges(path):
                chunk = _chunk("test" if info.is_test else "source_code", text, relative, counter)
                chunk.metadata.update(
                    {
                        "path": relative,
                        "line_start": start,
                        "line_end": end,
                        "is_test": info.is_test,
                        "changed": info.changed,
                        "language": info.language,
                    }
                )
                chunks.append(chunk)


def _dependency_distances(
    analysis: RepositoryAnalysis | None,
    terms: set[str],
    max_depth: int,
) -> dict[str, int]:
    if analysis is None or max_depth < 0:
        return {}
    symbols = [symbol for info in analysis.files.values() for symbol in info.symbols]
    by_short: dict[str, list[str]] = defaultdict(list)
    calls: dict[str, list[str]] = {}
    for symbol in symbols:
        qualified = symbol.qualified_name.casefold()
        by_short[symbol.name.casefold()].append(qualified)
        calls[qualified] = [call.casefold() for call in symbol.calls]

    distances: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()
    for symbol in symbols:
        qualified = symbol.qualified_name.casefold()
        if symbol.name.casefold() in terms or qualified in terms:
            distances[qualified] = 1
            distances[symbol.name.casefold()] = 1
            queue.append((qualified, 0))

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for call in calls.get(current, []):
            short = call.rsplit(".", 1)[-1]
            for target in by_short.get(short, []):
                distance = depth + 2
                if target not in distances or distance < distances[target]:
                    distances[target] = distance
                    distances[short] = min(distance, distances.get(short, distance))
                    queue.append((target, depth + 1))
    return distances


def _chunk(
    kind: str,
    text: str,
    source: str,
    counter: TokenCounter,
    *,
    mandatory: bool = False,
) -> ContextChunk:
    digest = hashlib.sha1(f"{kind}\0{source}\0{text}".encode()).hexdigest()[:12]
    return ContextChunk(
        id=f"{kind}:{digest}",
        kind=kind,
        text=text,
        source=source,
        token_count=counter.count(text),
        mandatory=mandatory,
    )
