---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-5050.json
qaCommit: bad7a36d817618e658330e78f366ce747f189f94
---

# PR #5078 QA Report: Import-Graph Test Selection

## Scope

Validated the import-graph test selection system: graph builder with caching,
fail-safe selector, pre-push hook integration, and CI workflow integration.

## Test Evidence

### Unit Tests (tests/test_selection/)
- Graph building from AST imports: PASS
- Cache staleness detection (pyproject.toml, source changes): PASS
- Fail-safe fallback for non-Python changes: PASS
- Fail-safe fallback for conftest changes: PASS
- Fail-safe fallback for runtime-read pattern matches: PASS
- Fail-safe fallback for dynamic imports: PASS
- Fail-safe fallback for unmapped files: PASS
- False-negative prevention (#4408 historical scenario): PASS

### Integration Tests
- Pre-push hook (git_hook_policy.py pytest): Full suite passes in 402s
- CI runner (run_pytest_selected.py): Partition args correct for all matrix entries
- merge_group event: Always runs full suite (unchanged)

### False-Green Prevention
- `.claude/rules/` change (issue #4408 scenario): correctly triggers FULL_SUITE fallback
- Non-Python file changes: correctly trigger FULL_SUITE fallback
- Stale graph cache: correctly triggers rebuild or FULL_SUITE fallback

## Verdict

PASS. All fail-safe paths verified. No false-negative path exists: every
uncertain case falls back to the full suite. The subset is always a superset
of truly-affected tests.
