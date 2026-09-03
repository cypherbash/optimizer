"""Deterministic conversation extraction and semantic extension point."""

from __future__ import annotations

import re
from dataclasses import fields
from typing import Protocol

from .models import ContextState, EvidenceItem, Importance, RejectedApproach


class SemanticExtractor(Protocol):
    def extract(
        self,
        task: str,
        conversation: str,
        deterministic_state: ContextState,
    ) -> ContextState:
        """Return an enriched state without discarding deterministic evidence."""


class NoOpSemanticExtractor:
    def extract(
        self,
        task: str,
        conversation: str,
        deterministic_state: ContextState,
    ) -> ContextState:
        return deterministic_state


FILE_PATTERN = re.compile(
    r"(?<![\w.-])(?:[\w.-]+[\\/])*[\w.-]+\."
    r"(?:py|pyi|js|jsx|ts|tsx|java|go|rs|rb|php|cs|cpp|c|h|hpp|md|rst|txt|"
    r"json|ya?ml|toml|ini|sh|bash|zsh|sql|html|css|scss|vue|svelte)(?![\w.-])",
    re.IGNORECASE,
)
CALLABLE_PATTERN = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\s*(?=\()")
QUOTED_IDENTIFIER_PATTERN = re.compile(r"[`\"]([A-Za-z_][\w.-]{1,80})[`\"]")
VERSION_PATTERN = re.compile(r"\b(?:Python\s*)?v?\d+\.\d+(?:\.\d+)?(?:\+)?\b", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://[^\s)>]+")
COMMAND_PATTERN = re.compile(
    r"^\s*(?:\$\s*)?(?:git|python|python3|pip|pytest|ruff|mypy|npm|pnpm|yarn|"
    r"cargo|go|make|docker|token-optimizer)\s+.+$",
    re.IGNORECASE,
)
HARD_CONSTRAINT_PATTERN = re.compile(
    r"\b(?:MUST(?:\s+NOT)?|REQUIRED|SHALL(?:\s+NOT)?|DO\s+NOT|DON'T|NEVER|"
    r"PRESERVE|WITHOUT\s+CHANGING|HAS\s+TO|HAVE\s+TO)\b",
    re.IGNORECASE,
)
SOFT_CONSTRAINT_PATTERN = re.compile(
    r"\b(?:SHOULD|PREFER|PREFERABLY|IDEALLY|MAY|OPTIONAL)\b", re.IGNORECASE
)
ERROR_PATTERN = re.compile(
    r"\b(?:error|exception|traceback|failed|failure|assertionerror|typeerror|"
    r"valueerror|keyerror|segfault|panic)\b",
    re.IGNORECASE,
)
QUESTION_PATTERN = re.compile(r"\?\s*$")
DECISION_PATTERN = re.compile(
    r"\b(?:decided|decision|we(?:'ll| will)|use|chosen|choose|keep|remain|owns)\b",
    re.IGNORECASE,
)
REJECT_PATTERN = re.compile(
    r"\b(?:rejected|not allowed|do not use|don't use|avoid)\b", re.IGNORECASE
)


def extract_state(
    task: str,
    conversation: str = "",
    semantic_extractor: SemanticExtractor | None = None,
) -> ContextState:
    """Extract facts conservatively; semantic enrichment can only add information."""

    state = ContextState(goal=task.strip())
    if task.strip():
        state.tasks.append(EvidenceItem(task.strip(), "task", Importance.CRITICAL, "task:full"))

    _extract_from_text(state, task, "task")
    _extract_from_text(state, conversation, "conversation")
    _deduplicate_state(state)

    extractor = semantic_extractor or NoOpSemanticExtractor()
    enriched = extractor.extract(task, conversation, state)
    _deduplicate_state(enriched)
    return enriched


def _extract_from_text(state: ContextState, text: str, source: str) -> None:
    in_code_block = False
    code_language = ""
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            code_language = stripped[3:].strip().lower() if in_code_block else ""
            continue
        if not stripped:
            continue
        provenance = f"{source}:line:{line_number}"

        if HARD_CONSTRAINT_PATTERN.search(stripped):
            _add(state.hard_constraints, stripped, source, Importance.CRITICAL, provenance)
        elif SOFT_CONSTRAINT_PATTERN.search(stripped):
            _add(state.soft_constraints, stripped, source, Importance.MEDIUM, provenance)

        if ERROR_PATTERN.search(stripped):
            _add(state.current_errors, stripped, source, Importance.CRITICAL, provenance)
        if QUESTION_PATTERN.search(stripped):
            _add(state.open_questions, stripped, source, Importance.MEDIUM, provenance)
        if re.search(r"\b(?:currently|current behavior|today|now)\b", stripped, re.I):
            _add(state.current_behavior, stripped, source, Importance.HIGH, provenance)
        if re.search(r"\b(?:desired behavior|should become|expected|want|goal)\b", stripped, re.I):
            _add(state.desired_behavior, stripped, source, Importance.HIGH, provenance)
        if re.search(r"\b(?:assume|assumption|presume)\b", stripped, re.I):
            _add(state.assumptions, stripped, source, Importance.MEDIUM, provenance)

        if REJECT_PATTERN.search(stripped):
            state.rejected_approaches.append(
                RejectedApproach(
                    approach=stripped,
                    reason=_rejection_reason(stripped),
                    source=source,
                )
            )
        elif DECISION_PATTERN.search(stripped) and not QUESTION_PATTERN.search(stripped):
            _add(state.decisions, stripped, source, Importance.HIGH, provenance)

        if in_code_block and (
            code_language in {"sh", "bash", "shell", "console"} or COMMAND_PATTERN.match(stripped)
        ):
            _add(state.recent_actions, stripped, source, Importance.MEDIUM, provenance)
        elif COMMAND_PATTERN.match(stripped):
            _add(state.recent_actions, stripped, source, Importance.MEDIUM, provenance)

        for filename in FILE_PATTERN.findall(stripped):
            _add(state.relevant_files, filename, source, Importance.HIGH, provenance)
        for identifier in CALLABLE_PATTERN.findall(stripped):
            _add(state.important_identifiers, identifier, source, Importance.HIGH, provenance)
        for identifier in QUOTED_IDENTIFIER_PATTERN.findall(stripped):
            _add(state.important_identifiers, identifier, source, Importance.MEDIUM, provenance)
        for version in VERSION_PATTERN.findall(stripped):
            _add(state.relevant_facts, f"Version: {version}", source, Importance.HIGH, provenance)
        for url in URL_PATTERN.findall(stripped):
            _add(state.relevant_facts, f"URL: {url}", source, Importance.MEDIUM, provenance)


def _rejection_reason(text: str) -> str:
    for separator in (" because ", " since ", " reason: ", " — ", " - "):
        if separator in text.lower():
            index = text.lower().index(separator)
            return text[index + len(separator) :].strip() or "Explicitly rejected"
    return "Explicitly rejected; no reason was stated"


def _add(
    collection: list[EvidenceItem],
    text: str,
    source: str,
    importance: Importance,
    provenance: str,
) -> None:
    collection.append(EvidenceItem(text, source, importance, provenance))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _deduplicate_state(state: ContextState) -> None:
    """Remove exact normalized repeats only; near-duplicates may differ in scope."""

    for descriptor in fields(state):
        value = getattr(state, descriptor.name)
        if not isinstance(value, list) or not value:
            continue
        seen: set[tuple[str, ...]] = set()
        result: list[object] = []
        for item in value:
            if isinstance(item, EvidenceItem):
                key = (_normalize(item.text), item.source)
            elif isinstance(item, RejectedApproach):
                key = (_normalize(item.approach), _normalize(item.reason), item.source)
            else:
                result.append(item)
                continue
            if key not in seen:
                seen.add(key)
                result.append(item)
        setattr(state, descriptor.name, result)
