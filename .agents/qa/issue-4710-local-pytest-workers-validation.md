---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-12-session-14694-b79ce74f8-fix-issue-4710-local-pytest.json
qaCommit: f70d63cf34e4c16cf8fcfa0660d68be9d1ae6a3b
---

# Issue 4710 local pytest worker validation

## Result

PASS. Local pre-push pytest now uses four workers. CI and direct invocations
retain xdist `auto`. The parent removes the worker-control variable before
starting child pytest processes.

## Evidence

- 875 worker-policy and Lefthook integration tests passed.
- The full four-worker hook suite passed 27,745 tests with 37 skipped.
- Mutation, safe-push, and pr-autofix partitions also passed.
- Ruff and `lefthook validate` passed.
- GPT-5.6 Sol code review returned `PASS`.
- Security review returned `APPROVED`, risk score 1 of 10.

## Scope

The change alters local pre-push scheduling only. It removes no tests, hooks,
selectors, or validation commands.
