# Agent Error Recovery Obligations

**Last Updated**: 2026-04-10
**Sessions Analyzed**: 1

## Constraints (HIGH confidence)

- When a git push or commit fails, read the error output and fix immediately. Do not stop and wait for the user to notice. (Session 2, 2026-04-10)
  - Evidence: Agent stopped after push failure on mypy errors, user had to say "you keep dying on git add or git push and then just...stop"
  - Root cause: Agent treated tool errors as conversation-ending instead of actionable

- When creating session logs, check the schema by reading an existing valid session log on the same branch, not by guessing fields. (Session 2, 2026-04-10)
  - Evidence: 2 failed commits due to missing session log fields (branchVerified, notOnMain, markdownLintRun, checklistComplete, changesCommitted, validationPassed, serenaMemoryUpdated)
  - Fix: Read a passing session log first, match its structure exactly