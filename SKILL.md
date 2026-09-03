---
name: optimize-coding-context
description: Build compact, audited context for a coding task from a conversation and repository while preserving constraints, decisions, APIs, errors, and relevant code.
---

# Optimize coding context

Use this repository when a coding agent needs a smaller, inspectable task context rather than an
aggressive prose summary.

## Workflow

1. Supply the exact user task and, when available, the raw conversation and repository.
2. Run deterministic extraction and repository analysis before considering any semantic or LLM
   extension.
3. Inspect extracted constraints, decisions, rejected approaches, errors, identifiers, and files.
4. Build ranked symbol-level context with the requested budget, recent-message count, context
   lines, and dependency depth.
5. Read warnings and the deterministic audit. Treat an audit failure as an incomplete result.
6. Use `--explain` when selection or omission needs review.

Typical command:

```bash
token-optimizer build \
  --task task.txt \
  --conversation conversation.md \
  --repo . \
  --budget 8000 \
  --output optimized-context.md \
  --stats \
  --explain
```

## Invariants

- Never remove important information solely to meet an arbitrary token target.
- Prefer deterministic repository analysis before spending LLM tokens.
- Keep the original user task and explicit mandatory constraints verbatim.
- Preserve recent raw messages because structured state cannot reconstruct all nuance.
- Keep rejected approaches together with their reasons.
- Do not upload repository or conversation content by default.
- If mandatory context exceeds the budget, return it with a warning. Use `--hard-budget` only
  when the user explicitly accepts possible correctness loss.
- Do not treat an audit pass as a guarantee of semantic completeness; review explanations for
  high-risk changes.
