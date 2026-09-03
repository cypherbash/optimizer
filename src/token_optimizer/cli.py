"""Command-line interface for the offline optimizer."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .audit import audit_context
from .context_builder import BuildOptions, build_context, format_explanations
from .evaluation import evaluate_result
from .models import ContextState
from .repo_analyzer import analyze_repository
from .serialization import dumps, load_file, write_file
from .state_extractor import extract_state
from .tokenizer import get_token_counter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="token-optimizer",
        description="Build correctness-first context for coding agents.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    count = subparsers.add_parser("count", help="Count or estimate tokens in a file")
    count.add_argument("file", type=Path)
    _add_tokenizer_options(count)

    extract = subparsers.add_parser("extract", help="Extract structured context state")
    extract.add_argument("--task", type=Path, required=True)
    extract.add_argument("--conversation", type=Path)
    extract.add_argument("--output", type=Path)
    extract.add_argument("--format", choices=("yaml", "json"), default="yaml")

    analyze = subparsers.add_parser("analyze-repo", help="Analyze a repository locally")
    analyze.add_argument("repository", type=Path)
    analyze.add_argument("--output", type=Path)
    analyze.add_argument("--format", choices=("yaml", "json"), default="yaml")

    build = subparsers.add_parser("build", help="Build optimized coding-agent context")
    _add_build_options(build)
    build.add_argument("--output", type=Path)
    build.add_argument("--state-output", type=Path)
    build.add_argument("--stats", action="store_true")
    build.add_argument("--stats-json", action="store_true")
    build.add_argument("--explain", action="store_true")
    build.add_argument("--explain-output", type=Path)

    audit = subparsers.add_parser("audit", help="Audit optimized context against state")
    audit.add_argument("--state", type=Path, required=True)
    audit.add_argument("--context", type=Path, required=True)
    audit.add_argument("--json", action="store_true")

    explain = subparsers.add_parser("explain", help="Explain selected and dropped chunks")
    _add_build_options(explain)
    explain.add_argument("--selected-only", action="store_true")

    benchmark = subparsers.add_parser("benchmark", help="Run a local selection evaluation")
    benchmark.add_argument("--fixture", type=Path, required=True)
    benchmark.add_argument("--json", action="store_true")
    _add_tokenizer_options(benchmark)
    return parser


def _add_build_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--conversation", type=Path)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--budget", type=int, default=8_000)
    parser.add_argument("--recent-messages", type=int, default=6)
    parser.add_argument("--context-lines", type=int, default=15)
    parser.add_argument("--dependency-depth", type=int, default=2)
    parser.add_argument("--hard-budget", action="store_true")
    _add_tokenizer_options(parser)


def _add_tokenizer_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tokenizer", choices=("auto", "estimate", "tiktoken"), default="auto")
    parser.add_argument("--model", default="gpt-4o-mini")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "count":
        text = args.file.read_text(encoding="utf-8", errors="replace")
        counter = get_token_counter(args.tokenizer, args.model)
        print(f"Tokens: {counter.count(text)}")
        print(f"Characters: {len(text)}")
        print(f"Lines: {len(text.splitlines())}")
        return 0

    if args.command == "extract":
        task = _read(args.task)
        conversation = _read(args.conversation)
        rendered = dumps(extract_state(task, conversation).to_dict(), args.format)
        _emit_or_write(rendered, args.output)
        return 0

    if args.command == "analyze-repo":
        rendered = dumps(analyze_repository(args.repository).to_dict(), args.format)
        _emit_or_write(rendered, args.output)
        return 0

    if args.command in {"build", "explain"}:
        result = _run_build(args)
        if args.command == "explain":
            print(format_explanations(result, include_dropped=not args.selected_only), end="")
            return 0
        _emit_or_write(result.context, args.output)
        if args.state_output:
            write_file(args.state_output, result.state.to_dict())
        explanation = format_explanations(result)
        if args.explain_output:
            args.explain_output.parent.mkdir(parents=True, exist_ok=True)
            args.explain_output.write_text(explanation, encoding="utf-8")
        if args.explain:
            print(explanation, file=sys.stderr, end="")
        if args.stats_json:
            print(json.dumps(result.statistics.to_dict(), indent=2), file=sys.stderr)
        elif args.stats:
            print(_format_statistics(result), file=sys.stderr)
        for warning in result.budget.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        return 0 if result.audit.passed else 1

    if args.command == "audit":
        state = ContextState.from_dict(load_file(args.state))
        result = audit_context(state, _read(args.context))
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print("PASS" if result.passed else "FAIL")
            for category in result.missing_categories:
                print(f"Missing: {category}")
            for warning in result.warnings:
                print(f"Warning: {warning}")
            for recommendation in result.recommendations:
                print(f"Recommendation: {recommendation}")
        return 0 if result.passed else 1

    if args.command == "benchmark":
        fixture = load_file(args.fixture)
        base = args.fixture.parent
        options = BuildOptions(
            tokenizer=args.tokenizer, model=args.model, budget=fixture.get("budget", 6000)
        )
        result = build_context(
            _read(base / fixture["task"]),
            _read(base / fixture.get("conversation", "")) if fixture.get("conversation") else "",
            base / fixture["repository"],
            options=options,
        )
        metrics = evaluate_result(
            result,
            expected_relevant_files=fixture.get("expected_relevant_files", []),
            expected_irrelevant_files=fixture.get("expected_irrelevant_files", []),
        )
        if args.json:
            print(json.dumps(metrics.to_dict(), indent=2))
        else:
            for name, value in metrics.to_dict().items():
                print(f"{name}: {value:.3f}")
        return 0 if result.audit.passed else 1

    raise ValueError(f"Unsupported command: {args.command}")


def _run_build(args: argparse.Namespace):
    options = BuildOptions(
        budget=args.budget,
        recent_messages=args.recent_messages,
        context_lines=args.context_lines,
        dependency_depth=args.dependency_depth,
        hard_budget=args.hard_budget,
        tokenizer=args.tokenizer,
        model=args.model,
    )
    return build_context(
        _read(args.task),
        _read(args.conversation),
        args.repo,
        options=options,
    )


def _read(path: Path | None) -> str:
    return path.read_text(encoding="utf-8") if path else ""


def _emit_or_write(text: str, path: Path | None) -> None:
    if path is None:
        print(text, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _format_statistics(result) -> str:
    stats = result.statistics
    lines = [
        "Original context",
        "----------------",
        f"Conversation:        {stats.original_conversation_tokens:>8,} tokens",
        f"Repository selected: {stats.repository_candidate_tokens:>8,} tokens",
        f"Total candidates:    {stats.total_candidate_tokens:>8,} tokens",
        "",
        "Optimized context",
        "-----------------",
    ]
    for kind, count in stats.selected_by_kind.items():
        lines.append(f"{kind.replace('_', ' ').title():<22}{count:>8,}")
    lines.extend(
        [
            "                       --------",
            f"Total:                {stats.optimized_tokens:>8,}",
            "",
            f"Reduction: {stats.reduction_percent:.1f} %",
            f"Budget:    {stats.requested_budget:,}",
            f"Audit:     {'PASS' if stats.audit_passed else 'FAIL'}",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
