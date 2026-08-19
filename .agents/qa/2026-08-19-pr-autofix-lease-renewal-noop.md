---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-19-session-99919-bc967748c-critical-review-open-issues-prs.json
qaCommit: a1617fd422796dac56c7db6677058db9379d06ef
---

# QA: pr-autofix lease renewal no-op fix (issue #5160)

## Scope

`.claude/skills/github/scripts/pr/pr_autofix_lease.py` (+ generated mirror at
`src/copilot-cli/skills/github/scripts/pr/pr_autofix_lease.py`),
`tests/test_pr_autofix_lease.py`.

## Evidence

- `uv run --frozen python -m pytest tests/test_pr_autofix_lease.py -q`:
  161 passed (including 2 new/modified tests covering the no-op path:
  `test_renew_on_own_live_lease_extends_ttl` re-scoped to the near-expiry
  write path with `post.call_count == 1`;
  `test_renew_on_own_live_lease_with_ample_ttl_is_a_noop` added, asserting
  `reason == "self-renew-noop"` and `post.call_count == 0`).
- `uv run --frozen ruff check .claude/skills/github/scripts/pr/pr_autofix_lease.py tests/test_pr_autofix_lease.py`:
  All checks passed.
- `uv run --frozen mypy .claude/skills/github/scripts/pr/pr_autofix_lease.py`:
  6 pre-existing `dict` type-arg errors confirmed present on unmodified
  `origin/main` at the same line offsets (stashed working tree and re-ran to
  verify); zero new errors introduced.
- `uv run --frozen python scripts/sync_plugin_lib.py` then
  `uv run --frozen python build/scripts/build_all.py`: regenerated the
  Copilot mirror; `diff` against the `.claude/` source confirms byte parity.
- `uv run --frozen python scripts/validation/pre_pr.py`: RESULT: All
  validations passed (full run, see session log work log).

## Verdict

PASS. Behavior change is scoped to `acquire()`'s self-renew branch only when
`renewing=True`; a fresh `acquire` call's self-renew classification is
unaffected (matches existing test coverage at `TestAcquire`, none of which
pass `renewing=True`).
