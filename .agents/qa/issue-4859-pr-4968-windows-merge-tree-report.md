---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14697-b1a84f1bc-recover-issue-4859-reassess-windows.json
qaCommit: 6d52dd5907897f61947f215884548280f3838994
---

# QA Report: Issue 4859 Windows merge-tree ratchet

## Scope

Validated Windows checkout prefix handling and transient scratch cleanup at
commit `6d52dd5907897f61947f215884548280f3838994`.

## Control Evidence

- Exact `origin/main` commit `784ad3d21aeb259e188de8352c4aef88de484819`
  failed `test_merge_tree_ruff_count_matches_direct_count_on_windows`.
  The merge-tree command returned exit 3 instead of exit 0.
- The same control failed
  `test_remove_tree_retries_transient_permission_error`.
  The prior implementation had no cleanup retry path.

## Fixed Evidence

- `tests/ci/test_merge_tree_materialization.py`: 18 passed.
- Five affected merge-tree test files: 66 passed.
- Windows read-only Git object cleanup now clears the attribute through
  `shutil.rmtree(onexc=...)` before retrying removal.
- Concurrent child removal and non-permission failure controls passed.
- Main merge preserved Git symlink materialization and its read-only integration control.
- Scoped Ruff on both changed Python files: passed.
- Direct Ruff ratchet: 27 equals baseline 27.
- Merge-tree ratchet passed after merging current `origin/main`.
- Repository pre-PR validation: 51 of 51 checks passed in 92.74 seconds.
- GPT-5.6 Sol artifact-only review returned `PASS`.
- The Windows path-contract test carries `pytest.mark.windows_path`.
  `.github/workflows/pytest.yml` runs that marker on `windows-latest`.

## Verdict

PASS. The control reproduces both defects. The branch passes positive,
negative, and edge checks without widening the fix.
