# Retrospective: Test Infrastructure Cluster (issues #3772, #3806, #3874, #3879, #3885, #3896, #3925, #3987, #4032)

**Date**: 2026-07-31
**Branch**: fix/test-infrastructure
**PR**: #4074

## What happened

Worked through a cluster of test-infrastructure issues focused on making the
test suite's green status trustworthy. Three categories of silent failure were
addressed: tests that never ran, mutation harnesses that could observe stale
bytecode, and test files that wrote to the repo working tree.

## Issues and outcomes

- **#3879** (nested tests never collected): Fixed 4 nested test functions by
  wrapping in `TestBlobIdentityAndRenameLookup`. Built `check_nested_tests.py`
  AST gate with 13 tests. Wired into pre_pr validation.

- **#3874** (unreachable code gate): Built `check_unreachable_code.py` AST gate
  with 19 tests. Expanded to cover nested blocks (if/elif/else, for/while,
  try/except/finally). Wired into pre_pr validation.

- **#3896** (stale bytecode in mutation harnesses): Proved defect empirically
  with `os.utime` to force mtime collision. Fixed by purging `__pycache__`
  before each subprocess. 4 proof tests.

- **#4032** (context-mode WebFetch deadlock): Fixed by routing GitHub URLs
  through `github-url-intercept` skill in all 6 analyst agent surfaces. 14
  contract tests. Plugin manifests bumped.

- **#3772** (pytest writes to working tree): Built `check_test_tree_writes.py`
  static AST gate with 24 tests. Gate reports 0 findings on current codebase.
  All 4 instances from the issue were already fixed on main.

- **#3885** (false exit-code contracts): Both instances fixed on main. Added
  governance rule to TESTING-RIGOR.md. Closed with evidence.

- **#3987** (wall-clock linearity test): Closed as already-fixed by PR #4050.

## Learnings captured

1. The `type: ignore` ratchet in `scripts/ci/type_ignore_count_ratchet.py`
   catches new suppressions immediately. Use `cast()` to fix type errors
   without adding suppressions.

2. Subprocess calls that use `text=True` must also pin `encoding="utf-8"` or
   `test_subprocess_text_encoding.py` flags them.

3. Static AST gates (check_nested_tests.py, check_unreachable_code.py,
   check_test_tree_writes.py) are the right shape for catching test hygiene
   issues: they're deterministic, cheap, and can run as pre-pr gates.

4. For `shutil.copytree(src, dst)`, only the destination (dst) creates files.
   The source is a read-only operation. A detector must check which arg is
   the write target.

5. The global `flock /tmp/aiagents-push.lock` was adopted to prevent concurrent
   push races, but the race is per-ref, not per-repo. Two pushes to different
   branches cannot collide. The global lock serialized the entire fleet behind the
   7 to 15 minute pre-push hook, producing a 28-waiter convoy (issue #4283).
   Use a per-branch lock instead; see the GOTCHAS.md "Concurrent pushes" entry.
   Always verify the push landed with
   `git fetch origin <branch> && git log --oneline origin/<branch> -3`.
