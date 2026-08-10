---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10037.json
qaCommit: ee9f058bbdb88ca41475bf90f76964774f54e132
---
# PR #4793 required-check rename and pr-autofix validation

## Scope

PR #4793 changes required-check rename guidance, attribution guidance, always-on corpus figures, the pr-autofix mutation guard, generated Copilot mirrors, and regression tests.

## Result

PASS. The original process-group failure is fixed. The later fast-exit lease-loss review finding is fixed. All six review threads were replied to and resolved.

## Evidence

- Negative control: adding job control to the local harness reproduced the process-group setup failure before the fix.
- `TMPDIR=$PWD/.pytest_tmp uv run --frozen pytest tests/test_pr_autofix_late_live_state_gate.py --rootdir=. -q`: 26 passed in 3.17s.
- `uv run --frozen pytest tests/validation/test_always_on_corpus_claims.py -q`: 37 passed in 0.74s.
- `uv run --frozen python scripts/validation/pre_pr.py`: RESULT All validations passed, 50 passed, 0 failed, 0 skipped.
- Normal `git push origin HEAD:fix/required-check-rename-rule` ran pre-push hooks. Summary included `python-tests` passed in 760.12s and `pre-pr-validation` passed in 79.34s.
- Remote verification: local and remote branch SHA both equal `ee9f058bbdb88ca41475bf90f76964774f54e132`.

## Thread disposition

- `.claude/rules/ci-scripts.md` no-gap rename thread: fixed with old-plus-new emission sequence, `rules/branches/main` query, and `gh pr checks` blind-spot note. Replied and resolved.
- `.claude/rules/universal.md` attribution thread: fixed by requiring trailer evidence before naming a human from git or GitHub actor fields. Replied and resolved.
- `model-context-doctrine.md` percentage thread: fixed to 19.3% and regenerated the Copilot mirror. Replied and resolved.
- `.claude/rules/ci-scripts.md` mandatory rename thread: fixed with both continuous and gap sequences. Replied and resolved.
- `src/copilot-cli/skills/pr-autofix/SKILL.md` generated fast-exit thread: fixed by regenerating after canonical change. Replied and resolved.
- `.claude/commands/pr-autofix.md` fast-exit lease-loss thread: fixed by checking lease loss after fast child wait and adding `test_fast_exit_reports_lease_loss_after_wait`. Replied and resolved.
