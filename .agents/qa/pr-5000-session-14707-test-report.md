---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14707-acf145278-fix-4961-copilot-plugin-root.json
qaCommit: 223042927e5e158204c9a782a6fff328211de0fe
---

# Issue 4961 Session 14707 QA Report

## Scope

Validated the plugin `lib` resolution in
`.claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py`: candidate
order, isolated `RepoInfo` import validation, fallthrough past incomplete or
foreign plugin roots, and fail-closed exit 2 when no candidate is importable.

## Defect reproduction

Ran the pre-fix script (`git show origin/main:...`) and the fixed script under
the same environment. `GITHUB_WORKSPACE` was unset so the runner checkout could
not mask the result.

- Foreign `CLAUDE_PLUGIN_ROOT` with no `lib/`, valid `COPILOT_PLUGIN_ROOT`:

  ```text
  before: exit 2, "Plugin lib directory not found: /tmp/foreign-4961-nolib/lib"
  after:  exit 0, prints usage
  ```

- Foreign `CLAUDE_PLUGIN_ROOT` that ships its own `lib/` (context-mode shape),
  valid `COPILOT_PLUGIN_ROOT`:

  ```text
  before: exit 1, ModuleNotFoundError: No module named 'github_core'
  after:  exit 0, prints usage
  ```

## Results

- Review fix tests: PASS, 18 tests.

  ```text
  uv run pytest tests/skills/merge-resolver/test_resolve_lib_dir.py -q
  18 passed
  ```

- Scoped Ruff: PASS.

  ```text
  uv run ruff check .claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py \
    tests/skills/merge-resolver/test_resolve_lib_dir.py
  ```

## Coverage

| Case | Test |
|------|------|
| Candidate order and membership | `TestLibDirCandidates` (2 tests) |
| Copilot root preferred | `test_prefers_copilot_plugin_root` |
| Claude root when Copilot unset | `test_uses_claude_plugin_root_when_copilot_is_unset` |
| Foreign Claude root falls through (#4961) | `test_foreign_claude_root_falls_through_to_copilot_root` |
| Missing Copilot root falls through | `test_missing_copilot_root_falls_through_to_claude_root` |
| Foreign `lib/` without `github_core` rejected | `test_foreign_plugin_lib_without_core_package_is_rejected` |
| Partial `github_core` without `api.py` rejected | `test_partial_core_package_without_the_imported_module_is_rejected` |
| `api.py` with a missing transitive import rejected | `test_api_with_missing_transitive_module_is_rejected` |
| Import failure with empty stderr | `test_import_probe_reports_failure_without_stderr` |
| Import timeout | `test_import_probe_reports_timeout` |
| `GITHUB_WORKSPACE` checkout | `test_uses_github_workspace_when_no_plugin_root_is_valid` |
| Repo-relative fallback | `test_falls_back_to_repository_lib_when_no_variable_is_set` |
| Fail-closed exit 2 and message | `test_exits_2_when_no_candidate_carries_the_core_package` |
| End to end under Copilot CLI | `TestResolveLibDirCli` (4 subprocess tests) |

## Review round 1

`copilot-pull-request-reviewer` found that the candidate predicate accepted a
`github_core` directory on name alone, so a half-installed package would be
selected and the import would then raise `ModuleNotFoundError` (exit 1) rather
than fall through or exit 2. Confirmed and fixed in commit 271d20435: the
predicate now requires `github_core/api.py`, the module the script imports.
Mutant M5 reproduces the reported defect and is killed by 3 tests.

## Review round 2

`copilot-pull-request-reviewer` found that checking for `api.py` still allowed
an incomplete package whose imported sibling modules were absent. Fixed in
commit 223042927: each candidate now imports `RepoInfo` in an isolated Python
process before selection. Tests cover a missing transitive module, empty
stderr, timeout, and the subprocess CLI path.

## Verdict

PASS. The acceptance criteria in issue 4961 are met: both harness roots
resolve, foreign and incomplete roots fall through instead of ending the run,
and the fail-closed exit 2 path is preserved and asserted.
