---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10037.json
qaCommit: fcb82e727264ef61a41b90471234cf0f462996d0
---
# PR #4793 required-check rename and pr-autofix validation

## Scope

PR #4793 changes required-check rename guidance, attribution guidance, always-on corpus figures, the pr-autofix mutation guard, generated Copilot mirrors, and regression tests.

## Result

PASS. The original process-group failure is fixed. The later fast-exit lease-loss findings and CI race are fixed. All six review threads were replied to and resolved.

## Evidence

- Negative control: adding job control to the local harness reproduced the process-group setup failure before the fix.
- `uv run pytest -n auto tests/test_pr_autofix_late_live_state_gate.py -q`: 28 passed in 3.47s after adding spawned-child coverage.
- `for i in 1 2 3; do uv run pytest -q tests/test_pr_autofix_late_live_state_gate.py::test_fast_exit_reports_lease_loss_after_wait tests/test_pr_autofix_late_live_state_gate.py::test_fast_exit_stops_delayed_child_after_lease_loss || exit $?; done`: each run collected 4 items and passed.
- `uv run --frozen pytest tests/validation/test_always_on_corpus_claims.py -q`: 37 passed in 0.74s.
- `uv run --frozen python scripts/validation/pre_pr.py`: RESULT All validations passed, 50 passed, 0 failed, 0 skipped.
- Normal `git push origin HEAD:fix/required-check-rename-rule` ran pre-push hooks. Summary included `python-tests` passed in 760.12s and `pre-pr-validation` passed in 79.34s.
- QA content commit: `fcb82e727264ef61a41b90471234cf0f462996d0`. Later commits in this PR add QA evidence only under `.agents/`.

## Thread disposition

- `.claude/rules/ci-scripts.md` no-gap rename thread: fixed with old-plus-new emission sequence, `rules/branches/main` query, and `gh pr checks` blind-spot note. Replied and resolved.
- `.claude/rules/universal.md` attribution thread: fixed by requiring trailer evidence before naming a human from git or GitHub actor fields. Replied and resolved.
- `model-context-doctrine.md` percentage thread: fixed to 19.3% and regenerated the Copilot mirror. Replied and resolved.
- `.claude/rules/ci-scripts.md` mandatory rename thread: fixed with both continuous and gap sequences. Replied and resolved.
- `src/copilot-cli/skills/pr-autofix/SKILL.md` generated fast-exit thread: fixed by regenerating after canonical change. Replied and resolved.
- `.claude/commands/pr-autofix.md` fast-exit lease-loss thread: fixed by checking lease loss after fast child wait and adding `test_fast_exit_reports_lease_loss_after_wait`. Replied and resolved.
- `.claude/commands/pr-autofix.md` delayed-child thread: fixed by stopping the whole mutation process group before releasing the lease and adding `test_fast_exit_stops_delayed_child_after_lease_loss`. Replied and resolved.
