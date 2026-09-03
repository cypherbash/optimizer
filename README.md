# Token Context Optimizer

An offline-first, correctness-first context selector for coding agents.

Large agent contexts contain valuable constraints and code mixed with stale discussion, unrelated
files, and repeated explanations. Ordinary summarization can reduce tokens while accidentally
removing the API contract, rejected approach, exact identifier, or test that makes the change
correct. This tool instead extracts structured state, analyzes a repository deterministically,
ranks inspectable chunks, applies a conservative budget, and audits the result for loss.

The objective is not maximum compression. It is to choose the tokens most likely to help a coding
model make the correct change.

## Quick start

Python 3.12 or newer is required. The default path has no runtime dependencies or network calls.

```bash
python -m pip install -e .

token-optimizer build \
  --task examples/sample_task.txt \
  --conversation examples/sample_conversation.md \
  --repo examples/sample_repo \
  --budget 8000 \
  --output optimized-context.md \
  --stats \
  --explain
```

For an accurate compatible tokenizer when available:

```bash
python -m pip install -e ".[tokenizers]"
```

Without `tiktoken`, the optimizer automatically uses a deterministic estimator. PyYAML is also
optional; the dependency-free YAML path emits JSON, which is valid YAML 1.2.

## Commands

```text
token-optimizer count FILE
token-optimizer extract --task TASK --conversation CONVERSATION
token-optimizer analyze-repo REPOSITORY
token-optimizer build --task TASK --conversation CONVERSATION --repo REPOSITORY
token-optimizer audit --state STATE --context CONTEXT
token-optimizer explain --task TASK --conversation CONVERSATION --repo REPOSITORY
token-optimizer benchmark --fixture examples/evaluation.json
```

Useful build controls:

- `--budget`: desired content-token budget.
- `--recent-messages`: raw messages retained for wording and nuance; default 6.
- `--context-lines`: surrounding lines included around selected symbols; default 15.
- `--dependency-depth`: bounded expansion from referenced functions; default 2.
- `--stats` / `--stats-json`: human- or machine-readable measurements.
- `--explain` / `--explain-output`: reasons and scores for selected and dropped chunks.
- `--state-output`: persist reusable structured state.
- `--hard-budget`: allow explicit loss when mandatory context itself exceeds the budget.

By default, mandatory context is never silently removed. If the task, hard constraints, critical
errors, and conflicts exceed the requested budget, the output exceeds it and reports why.

## Architecture

```text
                         User task
                             |
                   deterministic extraction
                             |
              +--------------+--------------+
              |                             |
      conversation state              repository analysis
       + recent messages           AST + text + Git status/diff
              |                             |
              +--------------+--------------+
                             |
                      candidate chunks
                             |
                explainable relevance score
                             |
                 adaptive token budgeting
                             |
                 labeled optimized context
                             |
                  deterministic loss audit
```

Responsibilities remain separate:

- `state_extractor.py` preserves natural-language evidence and exposes a vendor-neutral semantic
  extraction protocol.
- `repo_analyzer.py` inventories files, parses Python with `ast`, records symbols, calls, imports,
  tests, line ranges, and read-only Git state.
- `relevance.py` creates symbol-level candidates and scores lexical, structural, dependency,
  decision, recency, test, and changed-file signals.
- `budget.py` protects mandatory chunks, uses category targets as soft reservations, and
  redistributes unused capacity.
- `context_builder.py` renders the selected context and records explanations and statistics.
- `audit.py` checks the result against the structured state and exposes a semantic-auditor
  protocol for future adapters.

The implementation uses exact normalized deduplication only. It deliberately does not merge
similar statements when scope, strength, timing, or exceptions might differ.

## Structured state

`extract` records the goal, tasks, hard and soft constraints, relevant facts, decisions, rejected
approaches and reasons, questions, identifiers, files, errors, current and desired behavior,
actions, assumptions, and conflicts. Evidence includes its source, importance, and line
provenance where practical. The schema is in `schemas/context-state.schema.json`.

Project and session state are ordinary files rather than hidden storage. A durable workflow can
keep architecture and decisions in `project-state.yaml`, then combine them with a temporary
`session-state.yaml`; persistence policy remains under the caller's control.

## Evaluation

Token reduction alone is not a success metric. The local benchmark reports:

- token reduction
- critical fact recall
- constraint recall
- relevant file recall
- irrelevant file rejection
- audit pass rate
- a multiplicative quality score that falls to zero when constraints are lost

Run the included fixture with:

```bash
token-optimizer benchmark --fixture examples/evaluation.json
```

## Privacy and security

The default execution path is local and makes no API calls. Repository content is read only to
build selected chunks. Complete source files are not written to debug logs. Semantic extraction
and semantic auditing are interfaces plus prompt templates, not enabled cloud operations.

## Limitations

- Python is the only language with structural AST analysis in the MVP; other recognized text
  files use bounded line windows.
- Relevance scoring and dependency discovery are deterministic heuristics, not semantic proof.
- The call graph matches names conservatively and does not resolve dynamic dispatch.
- The deterministic audit catches missing extracted evidence but cannot guarantee semantic
  completeness.
- Heading and code-fence overhead can put final rendered output slightly above a content budget;
  this is reported rather than hidden.

Use conservative budgets, inspect explanations, and keep mandatory-context protection enabled for
high-risk changes.

## Future improvements

Tree-sitter and language-server integration, embeddings or semantic reranking, explicit OpenAI or
other LLM adapters, incremental indexing, persistent project memory, richer call-graph analysis,
Git-history relevance, and larger benchmark datasets can be added behind the existing stage
boundaries. None are required for the local MVP.
