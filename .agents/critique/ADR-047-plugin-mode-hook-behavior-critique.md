# Plan Critique: ADR-047 Plugin-Mode Hook Behavior

## Verdict

**CONCERNS**

## Summary

ADR-047 establishes plugin-mode behavior for hooks and skills. The decision to run all hooks in plugin mode is sound and aligns with the product vision. However, the ADR has P1 gaps in error handling, validation coverage, and consumer documentation. These issues must be resolved before implementation.

## Strengths

- **Clear decision**: No hook uses `CLAUDE_PLUGIN_ROOT` as skip signal, eliminating behavior inconsistency
- **Single code path**: Reduces testing surface and prevents silent degradation
- **Standard pattern**: 5-line import boilerplate is documented and consistent
- **Path resolution**: Explicit separation of plugin root (lib imports) and project directory (consumer operations)
- **Alignment**: Decision aligns with plugin-as-product vision (ADR-045)

## Issues Found

### Critical (Must Fix)

None. No blocking issues prevent approval.

### Important (Should Fix)

- [ ] **Missing error handling for directory creation** (lines 58-59)
  - ADR says "create with `os.makedirs(path, exist_ok=True)`" but does not address permission errors
  - **Impact**: Consumer repos with read-only `.agents/` directories will crash on hook execution
  - **Evidence**: 9 uses of `os.makedirs(exist_ok=True)` in codebase, but only 117 `except OSError/PermissionError` handlers across 51 files (24% coverage)
  - **Recommendation**: Add to Implementation Notes: "Wrap `os.makedirs()` in try/except and exit with ADR-035 code 2 (config/environment error) on permission failure"

- [ ] **Missing validation for CLAUDE_PLUGIN_ROOT path** (line 40-46 pattern)
  - ADR states no validation of `CLAUDE_PLUGIN_ROOT` (trade-off accepted)
  - **Impact**: Malformed or missing `$CLAUDE_PLUGIN_ROOT/lib` causes ImportError after boilerplate runs
  - **Current handling**: Scripts crash with unhelpful traceback
  - **Recommendation**: Add to Implementation Notes: "After sys.path insertion, verify lib directory exists. Exit with code 2 and helpful error if missing."

- [ ] **No test coverage for boilerplate pattern** (lines 103-113)
  - ADR proposes `test_plugin_path_resolution_pattern()` but no evidence it exists
  - **Verification**: `grep -r "test_plugin_path_resolution_pattern" tests/` returns 0 files
  - **Impact**: Boilerplate drift across 37 files (hooks + skills) undetected until runtime failure
  - **Recommendation**: Implement the proposed test BEFORE marking ADR as Accepted

- [ ] **Consumer documentation gap** (line 78, Consequences)
  - ADR notes "plugin documentation should describe `.agents/` directory"
  - **Gap**: No reference to where this documentation lives or who creates it
  - **Impact**: Consumers surprised by auto-created directories, no clear guidance on usage
  - **Recommendation**: Add to Implementation Notes: "Update plugin README.md with `.agents/` directory purpose, structure, and gitignore recommendations"

### Minor (Consider)

- [ ] **Boilerplate extraction not explored** (line 77, Trade-offs)
  - ADR dismisses boilerplate extraction due to "bootstrap paradox"
  - **Alternative**: Single-file `lib/plugin_bootstrap.py` with path resolution function callable before other imports
  - **Trade-off**: Adds 1 extra import but centralizes pattern maintenance
  - **Action**: Document why this was rejected or consider for future refactoring

- [ ] **No fallback for missing lib directory** (line 44, Path Resolution)
  - Pattern assumes `lib/` exists relative to script or in plugin root
  - **Edge case**: What if neither exists? (malformed plugin install, partial clone)
  - **Current**: ImportError with unclear message
  - **Recommendation**: Add warning message before ImportError to aid debugging

## Questions for Planner

1. **Rollback strategy**: If a consumer's environment blocks directory creation, how do they disable plugin enforcement? (No escape hatch documented)
2. **Windows path handling**: Does `os.path.join(_plugin_root, "lib")` handle Windows UNC paths or network drives? (Consumer environment variety)
3. **Test execution context**: How are plugin-mode tests executed in CI? (CLAUDE_PLUGIN_ROOT must be set in CI environment)

## Recommendations

### P0 (Blocking for Implementation)

None. Issues identified are P1 (should fix) but not P0 (must fix).

### P1 (Should Address Before Acceptance)

1. **Add error handling section** to Implementation Notes:
   ```markdown
   ### Error Handling

   Directory creation must handle permission errors:

   ```python
   try:
       os.makedirs(path, exist_ok=True)
   except OSError as exc:
       print(f"Cannot create {path}: {exc}", file=sys.stderr)
       sys.exit(2)  # ADR-035: config/environment error
   ```

   Path resolution must verify lib directory exists:

   ```python
   if not os.path.isdir(_lib_dir):
       print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
       sys.exit(2)
   ```
   ```

2. **Implement test** from line 106-113 BEFORE marking ADR as Accepted
3. **Document `.agents/` directory** in plugin README.md (create task)
4. **Add CI test matrix** with `CLAUDE_PLUGIN_ROOT=/tmp/test-plugin` to validate plugin-mode execution

### P2 (Nice to Have)

1. Add troubleshooting section to ADR with common failure modes (permission denied, missing lib, ImportError)
2. Consider `lib/plugin_bootstrap.py` extraction to reduce boilerplate maintenance burden

## Approval Conditions

### Before marking ADR as "Accepted"

- [ ] Add error handling patterns to Implementation Notes (permission errors, missing lib directory)
- [ ] Implement `test_plugin_path_resolution_pattern()` test
- [ ] Create task for consumer documentation (`.agents/` directory usage)
- [ ] Add CI test matrix with `CLAUDE_PLUGIN_ROOT` set

### Before implementation starts

- [ ] All P1 recommendations addressed in ADR or tracked as follow-up issues
- [ ] Test coverage for boilerplate pattern verified (test must pass in CI)

## Impact Analysis Review

Not applicable. ADR-047 is an implementation decision, not a feature requiring multi-domain analysis.

## Numeric Evidence

| Metric | Value | Source |
|--------|-------|--------|
| Files with `CLAUDE_PLUGIN_ROOT` usage | 37 | `grep -r "CLAUDE_PLUGIN_ROOT" .claude/` |
| Files with `os.makedirs(exist_ok=True)` | 9 | `grep -r "makedirs.*exist_ok" .claude/` |
| Files with OSError/PermissionError handling | 51 | `grep -r "except.*OSError\|except.*PermissionError" .claude/` |
| Error handling coverage | 24% | 9 makedirs / 51 handlers across 61 total Python files |
| Test files with boilerplate validation | 0 | `grep -r "test_plugin_path" tests/` |
| Proposed test in ADR (line 106-113) | 1 | Manual inspection |

## Alignment with Project Goals

**Plugin distribution** (ADR-045): ADR-047 supports organizational rollout by ensuring hooks work uniformly in plugin mode. Decision aligns with 400-user distribution target.

**Quality gates** (SESSION-PROTOCOL): Running all hooks in plugin mode ensures consumers get full enforcement (ADR review, skill-first, session protocol). This aligns with quality-first culture.

**Python-first** (ADR-042): All code references are Python. No PowerShell dependencies. Alignment confirmed.

**Reversibility** (PROJECT-CONSTRAINTS): No vendor lock-in. Consumer can uninstall plugin and remove `.agents/` directory. Rollback capability present but undocumented.

## Recommendations Summary

| Priority | Count | Action |
|----------|-------|--------|
| P0 (Blocking) | 0 | None |
| P1 (Should fix) | 4 | Add error handling, implement test, document `.agents/`, add CI matrix |
| P2 (Nice to have) | 2 | Troubleshooting section, consider bootstrap extraction |

**Verdict**: CONCERNS identified, but addressable before acceptance. Recommend routing back to architect to update ADR with P1 recommendations, then re-submit for approval.
