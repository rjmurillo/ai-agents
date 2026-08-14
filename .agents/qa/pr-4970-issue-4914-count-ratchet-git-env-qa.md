---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14696-b8dd33c5e-fix-issue-4914-isolate-git_.json
qaCommit: b8727c8d32ae895e1dec6027d77c718271e44a6f
---

# PR 4970 QA Report (issue #4914)

## Verdict

PASS. Every gate below was re-run on commit `e009b85af365b3c479765fd914cadd7088cb007c`, the last commit
carrying non-evidence changes, before this evidence was added. The code fix itself
landed in `0cd0a70d3cb53df6ebbef8fc03dcf4fb3dcd61fd`; `e009b85af3` adds only the
Serena memory and its index rows.

## Scope

`scripts/ci/count_ratchet.py` and `scripts/ci/ruff_count_ratchet.py` ran every git
subprocess with the ambient environment. A `git push` from a linked worktree exports
`GIT_DIR` into the pre-push hook, and an exported `GIT_DIR` outranks the `-C <root>`
argument, so the counters read the pushing worktree instead of the root they were
handed. The fix adds `git_environment()` and routes every git call site through it.

## Defect reproduced before the fix

Run directly on git 2.43.0. A scratch repository tracks only `keep.py`; `GIT_DIR`
names a second repository that also tracks `scripts/validation/only_on_branch.py`.

```text
$ git -C <scratch> ls-files                          # clean environment
keep.py

$ GIT_DIR=<other gitdir> git -C <scratch> ls-files   # the WRONG tree
keep.py
scripts/validation/only_on_branch.py
```

Git exports the variable only from a linked worktree. Measured by dumping the hook
environment on both pushes:

| Push origin | `GIT_DIR` in the pre-push environment |
|-------------|----------------------------------------|
| Linked worktree | `<main>/.git/worktrees/<name>` |
| Ordinary checkout | absent |

## End-to-end, the issue's own failure

`ruff_count_ratchet.current_count(<scratch>)` against a scratch tree that does not
carry the branch-only file, with `GIT_DIR` pointing at a disposable repository that
does. Same command, isolation removed and then restored.

```text
before: ruff could not read <scratch>/scripts/validation/
        check_unreachable_after_terminator.py: No such file or directory (os error 2)
        current_count(scratch) -> None

after:  current_count(scratch) -> 0
```

The `None` is what `merge-tree-ratchet` and `pre-pr-validation` report as
`counter returned None`, and it is what blocked five pushes on PR #4912.

## Tests

`tests/ci/test_count_ratchet_git_environment.py`, 17 tests, run against real git
rather than a `subprocess.run` stand-in. A stand-in would assert that some dict was
passed and would pass just as happily if git ignored it, which is the whole question.

| Class | Count | What it pins |
|-------|-------|--------------|
| Positive | 6 | Correct listing with no `GIT_*` set; the strip preserves a clean environment unchanged; `PATH`, `HOME` and a `DIGIT_COUNT` lookalike survive |
| Negative | 5 | Foreign `GIT_DIR` must not reach `tracked_files`, `baseline_at_ref`, `baseline_absent_at_ref`, `changed_files`, or the `ruff_count_ratchet` duplicate |
| Edge | 4 | Lowercase `git_dir`; result is a copy, not a view; a non-repository still returns `None` rather than `[]`; launch failure still returns `None` |
| Guard | 2 | AST check that no git `subprocess.run` in either module omits `env=`, plus the guard's own negative control |

Two of those deserve naming. `test_foreign_git_dir_would_win_without_isolation`
asserts the override is still real, so the negative controls cannot start passing
for a reason unrelated to the fix. `test_tracked_files_still_reports_failure_under_isolation`
pins that isolation does not convert a git failure into an empty listing, which
would score a tree as zero violations and pass by failing.

### Tests fail without the fix

The isolation was reverted and the module re-run:

```text
8 failed, 9 passed
FAILED test_tracked_files_ignores_a_foreign_git_dir
FAILED test_tracked_files_still_reports_failure_under_isolation
FAILED test_baseline_at_ref_ignores_a_foreign_git_dir
FAILED test_baseline_absent_at_ref_ignores_a_foreign_git_dir
FAILED test_changed_files_ignores_a_foreign_git_dir
FAILED test_ruff_ratchet_baseline_at_ref_ignores_a_foreign_git_dir
FAILED test_every_git_subprocess_passes_an_env[count_ratchet]
FAILED test_every_git_subprocess_passes_an_env[ruff_count_ratchet]
```

Restored: `17 passed`.

## Gates

| Gate | Command | Result |
|------|---------|--------|
| Unit and integration | `uv run pytest tests/ci/ -q` | 2416 passed, 10 skipped |
| New module | `uv run pytest tests/ci/test_count_ratchet_git_environment.py -q` | 17 passed |
| Lint | `uv run ruff check scripts/ci/count_ratchet.py scripts/ci/ruff_count_ratchet.py` | All checks passed |
| ruff count ratchet | `python scripts/ci/ruff_count_ratchet.py --base-ref origin/main` | OK, count == baseline 27 |
| taste count ratchet | `python scripts/ci/taste_count_ratchet.py --base-ref origin/main` | OK, 580 <= 583 |
| type-ignore ratchet | `python scripts/ci/type_ignore_count_ratchet.py --base-ref origin/main` | OK, count == baseline 44 |
| subprocess encoding ratchet | `python scripts/ci/subprocess_encoding_count_ratchet.py --base-ref origin/main` | OK, count == baseline 238 |
| cli exit contract ratchet | `python scripts/ci/cli_exit_contract_ratchet.py --base-ref origin/main` | OK, count == baseline 27 |
| Pre-PR | `uv run python scripts/validation/pre_pr.py` | RESULT: All validations passed |
| Commit hooks | lefthook pre-commit and commit-msg | all green |

The real gate was also exercised under the defect's own conditions:
`GIT_DIR=<this worktree gitdir> python scripts/ci/ruff_count_ratchet.py --base-ref origin/main`
returned `OK (count == baseline 27)` with exit 0.

## Divergence from the canonical helper, and why

`scripts/ci/merge_tree_materialization.py::isolated_git_environment` is the existing
pattern. It was not imported. Two measured reasons, both recorded in the new helper's
docstring:

1. `count_ratchet` is stdlib-only by contract, because the gates run by path in CI.
   That module imports `scripts.cli_exec`, so importing it would put the project's
   import graph behind every ratchet.
2. That helper also blanks `HOME` and the global git config. These gates run git
   against the real checkout, where `actions/checkout` records `safe.directory` in
   the global config. Measured: a global `safe.directory` that `git config --get-all`
   returns under the ambient environment (rc 0) is invisible under that helper's
   environment (rc 1).

So the `GIT_*` half of its rule is mirrored verbatim, including `name.upper()`, and
nothing else is dropped.

## Residual risk

| Risk | Assessment |
|------|------------|
| A new git call site omits `env=` | Covered by the AST guard on both modules. A git call built outside a list literal would evade it; none exists today. |
| Stripping `GIT_*` breaks a needed variable | All four call sites are local read-only reads (`ls-files`, `diff`, `show`, `ls-tree`, `rev-parse`). None contacts a remote, so `GIT_SSH_COMMAND` and `GIT_ASKPASS` are not load-bearing. `GIT_EXEC_PATH` falls back to git's compiled-in path, and the canonical helper already strips it in the same hook context. |
| `ruff_count_ratchet.baseline_at_ref` is dead | It is a duplicate that only its own test calls. It was fixed rather than deleted; deleting it is out of scope and is recorded in the session log's next steps. |

## Review Fix Addendum (b8727c8d3)

Non-behavioral changes addressing Copilot review findings:

1. Episode JSON: corrected metrics.errors from 17 to 8 (matching source session)
2. Memory file: added non-binding disclaimer per knowledge-persistence.md
3. PR description: fixed QA evidence path reference

No code logic changes. All original test evidence remains valid.
