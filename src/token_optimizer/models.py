"""Typed values passed between optimizer stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Importance(StrEnum):
    """How harmful losing an extracted fact would be."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(slots=True)
class EvidenceItem:
    text: str
    source: str
    importance: Importance = Importance.MEDIUM
    provenance: str | None = None


@dataclass(slots=True)
class RejectedApproach:
    approach: str
    reason: str
    source: str = "conversation"
    importance: Importance = Importance.HIGH


@dataclass(slots=True)
class ContextState:
    """Loss-aware project and session knowledge extracted from user material."""

    goal: str = ""
    tasks: list[EvidenceItem] = field(default_factory=list)
    hard_constraints: list[EvidenceItem] = field(default_factory=list)
    soft_constraints: list[EvidenceItem] = field(default_factory=list)
    relevant_facts: list[EvidenceItem] = field(default_factory=list)
    decisions: list[EvidenceItem] = field(default_factory=list)
    rejected_approaches: list[RejectedApproach] = field(default_factory=list)
    open_questions: list[EvidenceItem] = field(default_factory=list)
    important_identifiers: list[EvidenceItem] = field(default_factory=list)
    relevant_files: list[EvidenceItem] = field(default_factory=list)
    current_errors: list[EvidenceItem] = field(default_factory=list)
    current_behavior: list[EvidenceItem] = field(default_factory=list)
    desired_behavior: list[EvidenceItem] = field(default_factory=list)
    recent_actions: list[EvidenceItem] = field(default_factory=list)
    assumptions: list[EvidenceItem] = field(default_factory=list)
    conflicts: list[EvidenceItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextState:
        evidence_fields = {
            "tasks",
            "hard_constraints",
            "soft_constraints",
            "relevant_facts",
            "decisions",
            "open_questions",
            "important_identifiers",
            "relevant_files",
            "current_errors",
            "current_behavior",
            "desired_behavior",
            "recent_actions",
            "assumptions",
            "conflicts",
        }
        kwargs: dict[str, Any] = {"goal": data.get("goal", "")}
        for name in evidence_fields:
            kwargs[name] = [
                EvidenceItem(
                    text=str(item["text"]),
                    source=str(item.get("source", "state")),
                    importance=Importance(item.get("importance", "medium")),
                    provenance=item.get("provenance"),
                )
                for item in data.get(name, [])
            ]
        kwargs["rejected_approaches"] = [
            RejectedApproach(
                approach=str(item["approach"]),
                reason=str(item.get("reason", "Reason not captured")),
                source=str(item.get("source", "state")),
                importance=Importance(item.get("importance", "high")),
            )
            for item in data.get("rejected_approaches", [])
        ]
        return cls(**kwargs)


@dataclass(slots=True)
class SymbolInfo:
    name: str
    qualified_name: str
    kind: str
    line_start: int
    line_end: int
    calls: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RepositoryFile:
    path: str
    language: str
    size_bytes: int
    line_count: int
    is_test: bool = False
    changed: bool = False
    imports: list[str] = field(default_factory=list)
    symbols: list[SymbolInfo] = field(default_factory=list)
    parse_error: str | None = None


@dataclass(slots=True)
class RepositoryAnalysis:
    root: Path
    files: dict[str, RepositoryFile] = field(default_factory=dict)
    tree: list[str] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)
    git_diff: str = ""
    git_diff_cached: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "tree": self.tree,
            "languages": self.languages,
            "changed_files": self.changed_files,
            "files": {path: _serialize(asdict(info)) for path, info in self.files.items()},
        }


@dataclass(slots=True)
class ContextChunk:
    id: str
    kind: str
    text: str
    source: str
    token_count: int
    relevance_score: float = 0.0
    dependency_score: float = 0.0
    recency_score: float = 0.0
    decision_score: float = 0.0
    score: float = 0.0
    mandatory: bool = False
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BudgetResult:
    selected: list[ContextChunk]
    dropped: list[ContextChunk]
    requested_budget: int
    mandatory_tokens: int
    selected_tokens: int
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AuditResult:
    passed: bool
    missing_categories: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BuildStatistics:
    original_conversation_tokens: int
    repository_candidate_tokens: int
    total_candidate_tokens: int
    selected_by_kind: dict[str, int]
    optimized_tokens: int
    requested_budget: int
    reduction_percent: float
    audit_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BuildResult:
    context: str
    state: ContextState
    budget: BudgetResult
    audit: AuditResult
    statistics: BuildStatistics


def _serialize(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value
