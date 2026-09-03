"""Offline repository inventory and Python structural analysis."""

from __future__ import annotations

import ast
import subprocess
from collections import Counter
from pathlib import Path

from .models import RepositoryAnalysis, RepositoryFile, SymbolInfo

IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
}

LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
    ".md": "markdown",
    ".rst": "rst",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}


class _PythonSymbolVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.symbols: list[SymbolInfo] = []
        self.imports: list[str] = []
        self.scope: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.extend(alias.name for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        prefix = "." * node.level + (node.module or "")
        self.imports.append(prefix)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = ".".join([*self.scope, node.name])
        self.symbols.append(
            SymbolInfo(
                name=node.name,
                qualified_name=qualified,
                kind="class",
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
            )
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node, "method" if self.scope else "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node, "method" if self.scope else "function")

    def _record_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        kind: str,
    ) -> None:
        qualified = ".".join([*self.scope, node.name])
        calls = sorted(
            {_call_name(call.func) for call in ast.walk(node) if isinstance(call, ast.Call)}
        )
        self.symbols.append(
            SymbolInfo(
                name=node.name,
                qualified_name=qualified,
                kind=kind,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                calls=[call for call in calls if call],
            )
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def analyze_repository(
    root: Path,
    *,
    max_file_bytes: int = 1_000_000,
) -> RepositoryAnalysis:
    """Collect repository structure without modifying it or using network services."""

    resolved = root.resolve()
    if not resolved.is_dir():
        raise ValueError(f"Repository path is not a directory: {root}")

    changed_files, diff, cached_diff = _git_context(resolved)
    changed_set = {path.replace("\\", "/") for path in changed_files}
    result = RepositoryAnalysis(
        root=resolved,
        changed_files=sorted(changed_set),
        git_diff=diff,
        git_diff_cached=cached_diff,
    )
    language_counts: Counter[str] = Counter()

    paths = sorted(
        path
        for path in resolved.rglob("*")
        if path.is_file() and not _is_ignored_path(path.relative_to(resolved))
    )
    for path in paths:
        relative = path.relative_to(resolved).as_posix()
        result.tree.append(relative)
        language = LANGUAGES.get(path.suffix.lower(), "other")
        if language == "other" or path.stat().st_size > max_file_bytes:
            continue
        info = _analyze_file(path, relative, language, relative in changed_set)
        result.files[relative] = info
        language_counts[language] += 1

    result.languages = dict(sorted(language_counts.items()))
    return result


def _is_ignored_path(relative: Path) -> bool:
    return any(part in IGNORED_DIRECTORIES or part.endswith(".egg-info") for part in relative.parts)


def _analyze_file(path: Path, relative: str, language: str, changed: bool) -> RepositoryFile:
    raw = path.read_text(encoding="utf-8", errors="replace")
    line_count = len(raw.splitlines())
    normalized = relative.casefold()
    is_test = (
        normalized.startswith("tests/")
        or "/tests/" in normalized
        or Path(relative).name.startswith("test_")
        or Path(relative).stem.endswith("_test")
    )
    info = RepositoryFile(
        path=relative,
        language=language,
        size_bytes=path.stat().st_size,
        line_count=line_count,
        is_test=is_test,
        changed=changed,
    )
    if language != "python":
        return info
    try:
        tree = ast.parse(raw, filename=relative)
    except SyntaxError as exc:
        info.parse_error = f"{exc.msg} at line {exc.lineno}"
        return info
    visitor = _PythonSymbolVisitor()
    visitor.visit(tree)
    info.imports = sorted(set(visitor.imports))
    info.symbols = visitor.symbols
    return info


def _git_context(root: Path) -> tuple[list[str], str, str]:
    # A nested folder may happen to live inside an unrelated checkout. Only use Git
    # state when the caller's repository root is itself a worktree root.
    if not (root / ".git").exists():
        return [], "", ""
    if _run_git(root, "rev-parse", "--is-inside-work-tree").strip() != "true":
        return [], "", ""
    status = _run_git(root, "status", "--porcelain", "--untracked-files=all")
    changed: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        candidate = line[3:].split(" -> ")[-1].strip().strip('"')
        if candidate:
            changed.append(candidate)
    return (
        changed,
        _run_git(root, "diff", "--no-ext-diff", "--unified=3"),
        _run_git(root, "diff", "--cached", "--no-ext-diff", "--unified=3"),
    )


def _run_git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout if completed.returncode == 0 else ""
