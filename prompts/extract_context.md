# Structured context extraction

Extract loss-aware coding context from the supplied task and conversation. Do not merely
summarize. Return structured data with: goal, tasks, hard constraints, soft constraints,
relevant facts, decisions, rejected approaches and their reasons, open questions, important
identifiers, relevant files, current errors, current behavior, desired behavior, recent actions,
assumptions, and conflicts.

Rules:

- Do not remove a constraint because it seems obvious.
- Do not reinterpret an explicit decision.
- Preserve exact filenames, commands, API names, symbols, versions, and quoted identifiers.
- Preserve rejection reasons together with their rejected approaches.
- If two statements conflict, preserve both and mark the conflict.
- Distinguish facts from assumptions.
- Attach provenance and an importance level (`critical`, `high`, `medium`, or `low`) where
  possible.
- Prefer omission over invention. Use empty collections when evidence is absent.

The deterministic state supplied alongside the text is a floor: enrich it, but never silently
delete its evidence.
