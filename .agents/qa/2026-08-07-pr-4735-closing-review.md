---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-06-session-10004-memory-index-duplicate.json
qaCommit: 2559c8e0f45fb7dbe2107bd42e347e6ea8cb63e0
---
# QA Report: PR #4735 Closing Review

**SHA**: 2559c8e0f45fb7dbe2107bd42e347e6ea8cb63e0
**Date**: 2026-08-08
**Scope**: Closing-review fixes and original #4705 memory-index parser/canonicalization fix

## Verdict

### QA Complete

All acceptance criteria verified. No blocking issues found.

## Summary

| Metric | Value |
|--------|-------|
| Focused tests executed at current SHA | 519 |
| Passed | 519 |
| Failed | 0 |
| Full Python tests collected | 24,713 |
| Full Python tests passed | 24,679 |
| Full Python tests skipped | 34 |
| Full Python suite exit code | 0 |
| Files changed vs main | 50 |
| Lines added | 7,299 |
| Lines deleted | 426 |

## Acceptance Criteria Evidence

### AC-1: Memory-index parser uses markdown-it (original #4705 fix)

**Status**: [PASS]

- `_extract_memory_reference_names` uses `_create_parser` from `markdown_parser` module
- CommonMark token stream correctly extracts link destinations from table cells
- Markdown links rendered inside raw HTML do not contribute references
- Links after void HTML elements remain visible to duplicate detection
- Duplicate detection works: Counter identifies repeated canonical references
- Unsafe destinations (percent escapes, backslashes, parentheses, query strings, fragments) are rejected with specific reasons
- Command: `uv run --frozen python scripts/validation/memory_index.py --ci` passed
- Tests: 148 passed in tests/test_validation_memory_index.py

### AC-2: Session-end --qa-report support

**Status**: [PASS]

- `--qa-report` argument added to `build_parser()`
- `_qa_report_evidence` validates path containment under configured QA artifact root
- Rejects reports outside QA root with ValueError
- Rejects nonexistent files
- SKILL.md documents the flag with usage example
- Tests: 39 passed in tests/skills/session/test_complete_session_log.py

### AC-3: Mandatory qaValidation fail-closed behavior

**Status**: [PASS]

- `_must_items_complete` requires qaValidation as a MUST item with Complete=True
- Missing qaValidation returns False (fail-closed)
- Incomplete qaValidation (Complete=False) returns False
- Missing handoff key returns False
- Completed evidence must resolve to an existing file under the configured QA artifact root
- Tracked logs honor an explicit validation head
- Historical batch validation without a current head stays compatible
- Creation mode remains exempt because no session-end evidence exists yet
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
- Command: `uv run --frozen python scripts/validation/check_python3_entrypoints.py` passed
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
- Tests: 9 passed in tests/test_session_deadlock_4425.py

### AC-10: Mandatory QA contract stays executable

**Status**: [PASS]

- Session initialization emits incomplete `qaValidation` as a required item
- Session validation requires `qaValidation`
- The owner accepts a QA report or a verified investigation-only exemption
- Investigation checks include committed, staged, unstaged, and untracked paths
- Rename checks inspect both old and new paths
- `StagedFiles` remains a compatibility alias for the full `ChangedFiles` set
- Unapproved QA skip evidence fails validation
- Session completion recovers after a prior failed validation run
- Dirty-state checks parse NUL-delimited rename source and destination paths
- Live negative control rejected all 18 non-exempt paths from `b5899d7b3b`
- Prior closing suite: 1,075 passed across parser, entrypoint, session, workflow, encoding, and owner suites
- Current QA validator and session-end suite: 519 passed

### AC-11: Investigation-only scope reaches the validation endpoint

**Status**: [PASS]

- The validator accepts an exact `--validation-head`
- Local pre-PR validation resolves current HEAD and passes it to each changed session log
- CI checks out the exact pull request head and passes that SHA to the validator
- Scope remains a fixed commit range, so working-tree changes cannot alter the verdict
- An unresolved local HEAD fails closed through an invalid validation endpoint
- Tests cover eligible, stale-ending, invalid-head, pre-PR, and CI paths

### AC-12: Machine-readable QA binding rejects stale or unrelated evidence

**Status**: [PASS]

- Leading YAML frontmatter requires exact `PASS`, session-log path, and full commit
- Session identity uses the canonical `.agents/sessions/*.json` form
- Configured artifact roots map that identity to the physical session file
- Session comparison head and ending commit must resolve to the same commit
- QA commit must be an ancestor of the validation head
- Every intervening commit is inspected, including code later reverted
- Rename detection is disabled, so moving code into an evidence directory cannot hide it
- PR file discovery checks current and previous filenames, so code renamed into
  QA, session, or episode evidence paths still requires QA
- Only session, QA, and episode evidence paths may follow the QA commit
- Deferred, failed, unrelated, abbreviated, non-ancestor, and stale reports fail
- Helper statement and branch coverage is 100%
- Mutation control killed verdict, session, commit, and rename-query bypasses,
  with zero survivors

## Commands and Results

| Command | Result |
|---------|--------|
| `uv run --frozen python scripts/validation/memory_index.py --ci` | Passed |
| `uv run --frozen python scripts/validation/check_python3_entrypoints.py` | Passed |
| Current QA validator and session-end suite | 519 passed in 25.85s |
| `uv run --frozen pytest tests/ -q` | 24,679 passed, 34 skipped, 0 failed in 921.34s |
| `uv run --frozen python scripts/validation/pre_pr.py` | 50 of 50 passed in 79.46s |
| QA helper statement and branch coverage | 123 statements, 38 branches, 100% |
| QA mutation control | 4 killed, 0 survived, 0 did not apply, inverted control passed |
| `diff .claude/.../complete_session_log.py src/copilot-cli/.../complete_session_log.py` | Identical |
| `diff .claude/.../test_complete_session_log.py src/copilot-cli/.../test_complete_session_log.py` | Identical |
| `uv run --frozen python build/scripts/build_all.py --check` | Passed |
| Scoped markdownlint wrapper | NOT LINTED: 0 of 1 files selected because `.agents/**` is excluded |
| QA report content through markdownlint stdin | Initial run found 2 issues; corrected report passed with exit 0 |
| Investigation eligibility negative control from `b5899d7b3b` | 20 changed, 18 violations, compatibility alias matched |
| Ruff on changed Python | Passed |
| GPT-5.6 Sol review of SHA 2559c8e0f4 and full code diff | CLEAN after recursive fixes: no Critical or High findings |
| Security review of workflow head checkout and SHA propagation | CLEAN |

## Earlier Evidence for the Original Validator Fix

| Check | Result |
|-------|--------|
| git_hook_policy.py full suite | 24,005 main + 34 safe-push passed, 32 skipped |
| pre_pr.py | 50/50 passed |
| build_all.py --check --platform copilot-cli | Passed |
| Focused session-end suite | 129 passed |
| Ruff lint | Passed |
| Script and Markdown portability | Passed |
| GPT-5.6 Sol review of SHA ed0214a30d and final evidence | CLEAN: no Critical or High findings |

## Coverage Assessment

- Memory-index parser rewrite: 148 tests cover parsing, canonicalization, raw HTML exclusion, duplicate detection, symlink rejection, path traversal, unsafe destinations
- Session-end suites cover new flags, fail-closed logic, ending commit lifecycle, QA report validation, owned evidence exclusion, and API compatibility
- Entrypoint checker: 29 tests cover transitive resolution, cycle detection, package initializer inspection
- Workflow guards: 21 tests cover CI integrity failure modes

The current 519-test focused run exercises QA evidence and session-end changes. The
prior 1,075-test run covers generated entrypoints, encoding rules, owner
workflows, and PR-head validation. The exact final code SHA passed 24,679
Python tests, with 34 skips and no failures.

## Findings by Severity

### P0 (Blocking)

None.

### P1 (Should fix before merge)

None.

### Resolved During Closing Review

- High: code renamed into an ignored `.agents/` evidence path could bypass the
  QA requirement because the PR files query returned only the destination.
  The query now returns `previous_filename`, and three regression cases cover
  QA, session, and episode destinations.

### P2 (Non-blocking observations)

None.

## Reconciliation

```text
Promised: markdown-it parser, duplicate detection, --qa-report, fail-closed qaValidation, owned evidence commits, Copilot mirrors, frozen entrypoints, transitive deps, --refresh-ending-commit, exact validation head, machine-readable QA binding
Delivered: All items verified at SHA 2559c8e0f45fb7dbe2107bd42e347e6ea8cb63e0
Gap: None
Result: PASS
```
