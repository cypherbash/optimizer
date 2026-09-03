"""Correctness-first context optimization for coding agents."""

from .context_builder import BuildOptions, build_context
from .models import AuditResult, ContextChunk, ContextState
from .tokenizer import EstimatingTokenCounter, TokenCounter, get_token_counter

__all__ = [
    "AuditResult",
    "BuildOptions",
    "ContextChunk",
    "ContextState",
    "EstimatingTokenCounter",
    "TokenCounter",
    "build_context",
    "get_token_counter",
]

__version__ = "0.1.0"
