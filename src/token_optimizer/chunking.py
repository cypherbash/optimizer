"""Text and source-range chunking utilities."""

from __future__ import annotations

import re
from pathlib import Path

MESSAGE_BOUNDARY = re.compile(
    r"(?im)^(?:(?:#{1,4}\s*)?(?:user|assistant|system|developer)\s*:|"
    r"(?:#{1,4}\s+)(?:user|assistant|system|developer)\b)"
)


def split_messages(conversation: str) -> list[str]:
    """Split common transcript formats without inventing missing roles."""

    matches = list(MESSAGE_BOUNDARY.finditer(conversation))
    if matches:
        parts: list[str] = []
        if conversation[: matches[0].start()].strip():
            parts.append(conversation[: matches[0].start()].strip())
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(conversation)
            parts.append(conversation[match.start() : end].strip())
        return [part for part in parts if part]

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", conversation) if part.strip()]
    return paragraphs or ([conversation.strip()] if conversation.strip() else [])


def recent_messages(conversation: str, limit: int = 6) -> list[str]:
    if limit <= 0:
        return []
    return split_messages(conversation)[-limit:]


def source_range(
    path: Path,
    line_start: int,
    line_end: int,
    context_lines: int = 15,
) -> tuple[str, int, int]:
    """Read a bounded, numbered source range with surrounding context."""

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return "", 1, 1
    start = max(1, line_start - context_lines)
    end = min(len(lines), line_end + context_lines)
    width = len(str(end))
    text = "\n".join(f"{number:>{width}} | {lines[number - 1]}" for number in range(start, end + 1))
    return text, start, end


def fixed_source_ranges(path: Path, window_lines: int = 120) -> list[tuple[str, int, int]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    chunks: list[tuple[str, int, int]] = []
    for zero_start in range(0, len(lines), window_lines):
        zero_end = min(len(lines), zero_start + window_lines)
        start, end = zero_start + 1, zero_end
        width = len(str(end))
        text = "\n".join(
            f"{number:>{width}} | {lines[number - 1]}" for number in range(start, end + 1)
        )
        chunks.append((text, start, end))
    return chunks
