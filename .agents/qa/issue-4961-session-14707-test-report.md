---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14707-acf145278-fix-4961-copilot-plugin-root.json
qaCommit: acf14527853378f89d27f63c2474b8d1df3d58ea
---

# Issue 4961 Session 14707 QA Report

## Scope

Validated the plugin `lib` resolution in
`.claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py`: candidate
order, per-candidate validation, fallthrough past a foreign plugin root, and
fail-closed exit 2 when no candidate carries `github_core`.

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

- Focused tests: PASS, 89 tests (12 new).

  ```text
  uv run --frozen python -m pytest tests/skills/merge-resolver/ \
    tests/test_plugin_path_resolution.py -q
  89 passed
  ```

- Full suite: PASS (`uv run --frozen python -m pytest tests/ -x -q
  --timeout=300` exited 0), and the pre-push `python-tests` job passed in
  336.86s.

- Mutation sweep: PASS, 4 mutants, 0 unexpected outcomes.

  | Mutant | Restores | Expected | Observed |
  |--------|----------|----------|----------|
  | M1 | Claude root ahead of Copilot root | DEAD | DEAD (2 failed) |
  | M2 | Accept any existing `lib/` (drop `github_core` check) | DEAD | DEAD (3 failed) |
  | M3 | Take the first candidate only (no fallthrough) | DEAD | DEAD (5 failed) |
  | M4 | Inverted control: reword one docstring line | SURVIVED | SURVIVED (12 passed) |

  The harness refuses an absent or ambiguous target, asserts the file changed
  on disk before running, clears `__pycache__` between runs, restores the file
  byte-identically after each mutant, and fails the sweep on pytest exit 4 or
  "no tests ran".

- Scoped Ruff: PASS.

  ```text
  uv run --frozen ruff check .claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py \
    tests/skills/merge-resolver/test_resolve_lib_dir.py
  ```

- Vendor portability: PASS, 160 grandfathered refs across 84 scripts
  (baseline 160).
- Taste count ratchet: PASS, 581 violations against baseline 583.
- Pre-PR validation: PASS, 51 validations.

## Coverage

| Case | Test |
|------|------|
| Candidate order and membership | `TestLibDirCandidates` (2 tests) |
| Copilot root preferred | `test_prefers_copilot_plugin_root` |
| Claude root when Copilot unset | `test_uses_claude_plugin_root_when_copilot_is_unset` |
| Foreign Claude root falls through (#4961) | `test_foreign_claude_root_falls_through_to_copilot_root` |
| Missing Copilot root falls through | `test_missing_copilot_root_falls_through_to_claude_root` |
| Foreign `lib/` without `github_core` rejected | `test_foreign_plugin_lib_without_core_package_is_rejected` |
| `GITHUB_WORKSPACE` checkout | `test_uses_github_workspace_when_no_plugin_root_is_valid` |
| Repo-relative fallback | `test_falls_back_to_repository_lib_when_no_variable_is_set` |
| Fail-closed exit 2 and message | `test_exits_2_when_no_candidate_carries_the_core_package` |
| End to end under Copilot CLI | `TestResolveLibDirCli` (2 subprocess tests) |

## Verdict

PASS. The acceptance criteria in issue 4961 are met: both harness roots
resolve, a foreign root falls through instead of ending the run, and the
fail-closed exit 2 path is preserved and asserted.
