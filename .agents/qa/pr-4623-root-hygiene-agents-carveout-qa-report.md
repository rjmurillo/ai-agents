---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-05-session-9999-pr-4623.json
qaCommit: 541ac224adb6319bcb683b0a267f86f54e45a236
---

# QA Report: PR #4623 - Root Hygiene and Agents Carveout

## Summary

Validated the CI remediation and original features in this PR at commit `541ac224adb6319bcb683b0a267f86f54e45a236`:

1. **Root-hygiene pre-commit policy** - blocks staged files whose root entry is not in `ALLOWED_REPO_ROOT_ENTRIES`, skips during merge state, allows deletions of disallowed files.
2. **Implementer scaffold predicate change** - keys on `.agents/SESSION-PROTOCOL.md` presence rather than bare `.agents/` directory, preserving the "cannot list" hard-stop guard.
3. **Implementer scaffold evaluator alignment** - checks the consumer-install wording and block messages for the new ownership predicate across all generated prompts.

## Test Results

```
44 passed in 0.67s
```

```
22 passed in 0.19s
```

| Category | Count | Status |
|----------|-------|--------|
| Root-hygiene tests | 4 | [PASS] |
| CLI dispatch test | 1 | [PASS] |
| Configuration named-jobs test | 1 | [PASS] |
| Implementer scaffold predicate tests | 3 | [PASS] |
| Other collected tests | 35 | [PASS] |
| Implementer scaffold evaluator and predicate tests | 22 | [PASS] |

## Ruff Results

```
All checks passed!
```

No lint violations in `git_hook_policy.py`, `test_lefthook_integration.py`, `test_implementer_scaffold_predicate.py`, or `test_implementer_scaffold_gate.py`.

## Generator Validation

```
VALIDATION PASSED: All generated files match committed files
```

All 5 generated mirrors (`.claude/agents/implementer.md`, `.github/agents/implementer.agent.md`, `src/claude/implementer.md`, `src/copilot-cli/agents/implementer.agent.md`, `src/vs-code-agents/implementer.agent.md`) are in sync with the template after the merge resolution.

## Correctness Assessment

### Root-hygiene policy

- **MERGE_HEAD skip**: `check_root_hygiene` calls `_merge_in_progress(repo_root)` and returns 0 immediately if true. Test `test_root_hygiene_skips_merge_state` writes a synthetic MERGE_HEAD file and confirms exit 0 for a disallowed file. Correct.
- **Blocks untracked root scratch files**: If a file's root entry is not in the allowlist AND `_read_index_blob` returns non-None (file has staged content, i.e. not a deletion), the file is flagged. Test confirms exit 1 and stderr guidance. Correct.
- **Allows deletions**: When a disallowed root file is staged for deletion, `_read_index_blob` returns None (no blob in index for that path post-staging), so the file passes. Test confirms exit 0. Correct.
- **Allowlist sync**: Test `test_root_hygiene_allowlist_matches_current_tracked_root` asserts the frozen allowlist equals `git ls-tree --name-only HEAD` output. This ensures no drift between the allowlist and the actual repo root.

### Scaffold predicate change

- Keys on `.agents/SESSION-PROTOCOL.md` presence instead of bare `.agents/` or the HANDOFF/AGENT-INSTRUCTIONS pair.
- The "cannot list `.agents/`" hard-stop guard (`[BLOCKED] Cannot determine .agents scaffold ownership`) is preserved - merged in from main's version and retained.
- Consumer-owned `.agents/` directories without SESSION-PROTOCOL.md no longer trigger scaffold gates. This fixes #4580.

### Lefthook configuration

- `root-hygiene-policy` job added with `skip: [merge]` directive, consistent with the policy's own `_merge_in_progress` check (defense in depth).

## Residual Observations (Non-blocking)

1. The allowlist is a static frozen set. Adding a new root entry requires updating both the repo and the allowlist in the same commit. The sync test catches drift but only at test time, not at hook time for other contributors. This is documented behavior.
2. The `skip: [merge]` in lefthook.yml and the `_merge_in_progress` check in the policy are redundant by design (belt-and-suspenders). No issue.
3. Arrow characters in the generated mirror diff (`.claude/agents/implementer.md`) were replaced with colons in the new version, removing potential encoding ambiguity. No regression.

## Verdict

```
Promised: root-hygiene policy, scaffold predicate change, evaluator alignment, generated mirror sync, tests, lefthook config
Delivered: all of the above at HEAD 541ac224ad
Gap: none
Result: PASS
```

**Status**: PASS
**Confidence**: High
**Rationale**: The original 44 tests and the 22 CI-remediation evaluator and predicate tests pass, the linter is clean, the generator is in sync, logic is sound for all three policy behaviors, and no conflict artifacts were detected.
