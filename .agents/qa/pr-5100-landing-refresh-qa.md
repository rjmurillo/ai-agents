---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-5100-landing-refresh.json
qaCommit: 08875fedf04f0c25740fa77226e7333122ffe457
---

# PR 5100 QA Report

## Verdict

PASS. The workspace-budget display reconciliation matches validation semantics on commit `08875fedf`.

## Scope

- `scripts/validate_workspace_budget.py`
- `tests/test_validate_workspace_budget.py`
- `CONTRIBUTING.md`

## Evidence

- `uv run pytest tests/test_validate_workspace_budget.py -q`: 25 passed
- Manual run against a fixture tree: copilot-instructions at 4,000 bytes shows `(limit 6,351) [OK]` and rc=0; no `[OVER]` marker on a passing run
- Review-round hardening: the no-OVER test asserts rc == 0 unconditionally, pins the effective-ceiling label against `FILE_CEILING_BYTES`, and rejects the generic 3,000-byte label
- Ratchets at baseline: taste 583, ruff 27, type-ignore 44, subprocess-encoding 238
- `scripts/validation/check_generated_staleness.py`: 0 stale in 2 generator check(s), rc=0

## Not verified

- The issue #4883 validator-ownership item (overlap between this validator and `scripts/validation/passive_context_budget.py`) is out of this PR's scope and stays tracked on the issue; the PR body reference was downgraded to Refs accordingly.
