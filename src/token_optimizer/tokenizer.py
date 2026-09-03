"""Vendor-neutral token counting with an offline fallback."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Protocol


class TokenCounter(Protocol):
    def count(self, text: str) -> int:
        """Return a deterministic token count or estimate."""


@dataclass(slots=True)
class EstimatingTokenCounter:
    """Conservative approximation that behaves reasonably for prose and code."""

    characters_per_token: float = 4.0

    def count(self, text: str) -> int:
        if not text:
            return 0
        character_estimate = math.ceil(len(text) / self.characters_per_token)
        lexical_units = len(re.findall(r"[\w]+|[^\w\s]", text, flags=re.UNICODE))
        return max(character_estimate, lexical_units)


class TiktokenCounter:
    """Optional accurate counter, imported only when requested or available."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        import tiktoken  # type: ignore[import-not-found]

        try:
            self._encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            self._encoding = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text))


def get_token_counter(kind: str = "auto", model: str = "gpt-4o-mini") -> TokenCounter:
    """Return a real tokenizer when available, otherwise the offline estimator."""

    if kind not in {"auto", "estimate", "tiktoken"}:
        raise ValueError(f"Unknown tokenizer: {kind}")
    if kind == "estimate":
        return EstimatingTokenCounter()
    try:
        return TiktokenCounter(model)
    except ImportError:
        if kind == "tiktoken":
            raise RuntimeError(
                "tiktoken is not installed; install the 'tokenizers' extra"
            ) from None
        return EstimatingTokenCounter()
