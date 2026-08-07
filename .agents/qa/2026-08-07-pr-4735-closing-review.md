# QA Report: PR #4735 Closing Review

**SHA**: ed0214a30d1b4d763e4ec17a149c77c8db582814
**Date**: 2026-08-07
**Scope**: Closing-review fixes and original #4705 memory-index parser/canonicalization fix

## Verdict

**QA COMPLETE**

All acceptance criteria verified. No blocking issues found.

## Summary

| Metric | Value |
|--------|-------|
| Focused tests executed | 2,379 |
| Passed | 2,379 |
| Failed | 0 |
| Files changed vs main | 27 |
| Net lines added | 2,973 |

## Acceptance Criteria Evidence

### AC-1: Memory-index parser uses markdown-it (original #4705 fix)

**Status**: [PASS]

- `_extract_memory_reference_names` uses `_create_parser` from `markdown_parser` module
- CommonMark token stream correctly extracts link destinations from table cells
- Duplicate detection works: Counter identifies repeated canonical references
- Unsafe destinations (percent escapes, backslashes, parentheses, query strings, fragments) are rejected with specific reasons
- Command: `uv run python scripts/validation/memory_index.py --ci` passed (328 indexed, 0 missing, 0 keyword issues)
- Tests: 142 passed in tests/test_validation_memory_index.py

### AC-2: Session-end --qa-report support

**Status**: [PASS]

- `--qa-report` argument added to `build_parser()`
- `_qa_report_evidence` validates path containment under configured QA artifact root
- Rejects reports outside QA root with ValueError
- Rejects nonexistent files
- SKILL.md documents the flag with usage example
- Tests: 32 passed in tests/skills/session/test_complete_session_log.py

### AC-3: Mandatory qaValidation fail-closed behavior

**Status**: [PASS]

- `_must_items_complete` requires qaValidation as a MUST item with Complete=True
- Missing qaValidation returns False (fail-closed)
- Incomplete qaValidation (Complete=False) returns False
- Missing handoff key returns False
- Tests: 48 passed in tests/skills/test_session_scripts.py

### AC-4: Generated Copilot mirrors

**Status**: [PASS]

- `.claude/skills/session-end/scripts/complete_session_log.py` identical to `src/copilot-cli/skills/session-end/scripts/complete_session_log.py` (diff exit 0)
- `.claude/skills/session-end/tests/test_complete_session_log.py` identical to `src/copilot-cli/skills/session-end/tests/test_complete_session_log.py` (diff exit 0)

### AC-5: Frozen memory_index entrypoints

**Status**: [PASS]

- All 5 occurrences of `python3 scripts/validation/memory_index.py` in retrospective template replaced with `uv run --frozen python scripts/validation/memory_index.py`
- Zero remaining `python3 scripts/validation` references across all 6 retrospective agent files
- Compressed implementer prototype uses the frozen memory-index entrypoint
- `uv run --frozen python scripts/validation/traceability.py` also updated

### AC-6: Transitive dependency checks

**Status**: [PASS]

- `_collect_imports_recursive` traces through local imports with cycle detection via visited set
- `_candidate_module_files` inspects package `__init__.py` files
- `memory_index.py` correctly detected as transitively importing `markdown_it` (a third-party package)
- `check_python3_entrypoints.py` scan docs list expanded with 7 new retrospective agent files
- Command: `uv run python scripts/validation/check_python3_entrypoints.py` passed
- Tests: 29 passed in tests/test_check_python3_entrypoints.py

### AC-7: Session-end --refresh-ending-commit

**Status**: [PASS]

- `_set_ending_commit` sets new commit when empty, refreshes when `refresh=True`, skips when `refresh=False` and value exists
- Episode comparison head updated on refresh
- Commit truncated to 10 chars for storage
- Full SHA used for comparison head

### AC-8: Workflow fail-open guards

**Status**: [PASS]

- Tests: 21 passed in tests/workflows/test_workflow_fail_open_guards.py

### AC-9: Session evidence commit remains possible

**Status**: [PASS]

- `changesCommitted` excludes the owned session log and validated QA report
- Git status expands wholly untracked directories to file paths
- Unrelated modified files still fail the completion gate
- Existing `exclude_path` callers remain supported
- Tests: 7 passed in tests/test_session_deadlock_4425.py

## Commands and Results

| Command | Result |
|---------|--------|
| `uv run python scripts/validation/memory_index.py --ci` | PASSED: 33/33 domains, 328 files, 0 issues |
| `uv run python scripts/validation/check_python3_entrypoints.py` | OK: no bare-python3 invocations |
| `uv run python -m pytest tests/test_validation_memory_index.py -x -q` | 142 passed (1.56s) |
| `uv run python -m pytest tests/test_check_python3_entrypoints.py -x -q` | 29 passed (0.92s) |
| `uv run python -m pytest tests/skills/session/test_complete_session_log.py -x -q` | 32 passed (0.45s) |
| `uv run python -m pytest tests/skills/test_session_scripts.py -x -q` | 48 passed (0.59s) |
| `uv run python -m pytest tests/workflows/test_workflow_fail_open_guards.py -x -q` | 21 passed (0.60s) |
| `diff .claude/.../complete_session_log.py src/copilot-cli/.../complete_session_log.py` | Identical |
| `diff .claude/.../test_complete_session_log.py src/copilot-cli/.../test_complete_session_log.py` | Identical |

## Pre-existing Deterministic Evidence (reported by caller)

| Check | Result |
|-------|--------|
| git_hook_policy.py full suite | 24,005 main + 34 safe-push passed, 32 skipped |
| pre_pr.py | 50/50 passed |
| build_all.py --check --platform copilot-cli | Passed |
| Focused session-end suite | 129 passed |
| Ruff lint | Passed |
| Script and Markdown portability | Passed |
| Review tree identity vs tested 743c364 | Identical |
| GPT-5.6 Sol review of SHA ed0214a30d and final evidence | CLEAN: no Critical or High findings |

## Coverage Assessment

- Memory-index parser rewrite: 142 tests cover parsing, canonicalization, duplicate detection, symlink rejection, path traversal, unsafe destinations
- Session-end suites cover new flags, fail-closed logic, ending commit lifecycle, QA report validation, owned evidence exclusion, and API compatibility
- Entrypoint checker: 29 tests cover transitive resolution, cycle detection, package initializer inspection
- Workflow guards: 21 tests cover CI integrity failure modes

The 2,379 focused tests exercise changed public functions with positive, negative, and edge-case scenarios.

## Findings by Severity

### P0 (Blocking)

None.

### P1 (Should fix before merge)

None.

### P2 (Non-blocking observations)

None.

## Reconciliation

```
Promised: markdown-it parser, duplicate detection, --qa-report, fail-closed qaValidation, owned evidence commits, Copilot mirrors, frozen entrypoints, transitive deps, --refresh-ending-commit
Delivered: All items verified at SHA ed0214a30d1b4d763e4ec17a149c77c8db582814
Gap: None
Result: PASS
```
