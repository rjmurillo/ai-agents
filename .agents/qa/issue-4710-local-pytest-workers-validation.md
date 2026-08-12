---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-12-session-14694-b79ce74f8-fix-issue-4710-local-pytest.json
qaCommit: 353e8c578d8cf26fb805601a472c86ea4d9abe83
---

# Issue 4710 local pytest worker validation

## Result

PASS. Local pre-push pytest now uses up to four process-visible CPUs. CI and
direct invocations retain xdist `auto`. Explicit developer overrides still win.
The parent removes both worker-control variables before child pytest starts.

## Evidence

- 887 worker-policy and Lefthook integration tests passed.
- The capped hook partitions passed 27,853 tests with 37 skipped.
- Mutation, safe-push, and pr-autofix partitions also passed.
- Ruff and `lefthook validate` passed.
- GPT-5.6 Sol code review returned `PASS`.
- Security review returned `APPROVED`, risk score 1 of 10.

## Scope

The change alters local pre-push scheduling only. It removes no tests, hooks,
selectors, or validation commands.
