# Context preservation audit

Compare the original structured state with the optimized coding-agent context. Identify any
information needed to perform the task correctly that was lost, weakened, broadened, or assigned
to the wrong scope.

Check the task, mandatory constraints, decisions, compatibility promises, identifiers, relevant
files and interfaces, rejected approaches and reasons, current and desired behavior, critical
errors, tests, open questions, assumptions, and conflicts.

Prefer false positives over silently missing critical information. Exact wording need not match
when meaning and strength are demonstrably preserved, but exact identifiers and API contracts
must remain exact. Return `passed`, `missing_categories`, `warnings`, and `recommendations`.
