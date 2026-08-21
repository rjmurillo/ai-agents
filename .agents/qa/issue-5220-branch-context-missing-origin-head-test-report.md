---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-5220-session-log-false-positive.json
qaCommit: 36bfb510b2858c5f22e164cd42342d04921a250a
---

# QA Report: Issue #5220, check_branch_context hard-blocks after a merge when origin/HEAD is unset

## Summary

PASS. `_is_merged_history` now resolves the upstream default branch through a
two-rung fallback (`origin/HEAD`, then `origin/main`) instead of depending on
`origin/HEAD` alone. An initial three-rung version also fell back to local
`main`, matching `resolve_push_update`'s push-base ladder; a security review
(2026-08-21, see below) found that rung over-permissive for this call site and
it was dropped in a follow-up commit.

## Root Cause Verified

`_is_merged_history` in `scripts/validation/git_hook_policy.py` asked only
`git rev-parse --abbrev-ref origin/HEAD` and returned `False` the moment that
ref failed to resolve. `git clone` sets `origin/HEAD`; a fetch into an
already-initialised repo, a shallow or filtered clone, and several CI checkout
actions do not. Reproduced on this checkout before the fix:

```text
$ git rev-parse --abbrev-ref origin/HEAD
fatal: ambiguous argument 'origin/HEAD': unknown revision or path not in the working tree.
rc=128
$ git rev-parse --abbrev-ref origin/main
origin/main
rc=0
```

With `origin/HEAD` unresolved, `check_branch_context` blocked with the same
log names issue #5220 reports (`claude/pr-automerge-goal-eu2soz`,
`2026-08-21-session-99926-a1b2c3d4e-pr-automerge-goal.json`), confirming this
checkout hits the exact defect the issue describes.

## Security Review

`Task(subagent_type="security")` reviewed the three-rung version (the fix
before the follow-up commit) and returned three findings:

- **SEC-001 (Low, real, fixed)**: local `main` grants the exemption to a
  session log that only exists on the developer's own local `main`, the exact
  issue #682 co-mingling shape. Local `main` is writable by the same actor the
  check exists to catch, unlike `origin/main`. Fixed by dropping the rung in
  commit `c19f1e73c0786f5af43c67d8c6c14e7362f21d20`.
- **SEC-002 (Medium, rule violation, fixed)**: the docstring claimed the
  three-rung ladder "mirrors" `resolve_push_update` without noting
  `resolve_push_update`'s local-`main` fallback is conditional
  (`push_ref.is_new`) while the new one was not, violating
  `canonical-source-mirror.md`'s divergence-section requirement. Moot after
  SEC-001's fix removed the rung; the current docstring instead explains why
  the two-rung version is intentionally *stricter* than
  `resolve_push_update`.
- **SEC-003 (Medium, resolved by removal)**: the local-`main` rung had zero
  test coverage. Resolved by removing the rung rather than adding coverage for
  behavior that should not exist; a new negative test
  (`test_branch_context_merged_history_does_not_trust_local_main`) instead
  pins that local `main` is never trusted.

No injection risk, fail-open contract, or `_commit_ref_exists` peeling
behavior findings; all confirmed clean by direct read of the affected code.

## Evidence

| Check | Result |
|-------|--------|
| `uv run --frozen python -m pytest tests/test_lefthook_integration.py -k "branch_context" -q` | 22 passed |
| `uv run --frozen python -m pytest tests/test_lefthook_integration.py -q` | 865 passed, 1 skipped |
| `uv run --frozen ruff check scripts/validation/git_hook_policy.py tests/test_lefthook_integration.py` | All checks passed |
| `uv run --frozen mypy scripts/validation/git_hook_policy.py` | Success: no issues found in 1 source file |
| `uv run --frozen python scripts/validation/pre_pr.py` | 57 passed, 0 failed, 0 skipped; re-run against the final tree after the SEC-001 fix |
| Mutation check: reintroduce the local-`main` rung, re-run the new negative test | Fails (`assert 0 == 1`), confirming the test discriminates; reverted and re-confirmed byte-identical to the source file |

## Coverage

- **Positive**: `test_branch_context_merged_history_survives_missing_origin_head`
  proves the exemption still fires when `origin/HEAD` is absent, the winning
  log is merged history reachable only via `origin/main`, and the branch owns
  its own log. Negative control inside the same test asserts `origin/HEAD`
  really is unresolved in the fixture, so the assertion cannot pass for the
  wrong reason.
- **Negative**: `test_branch_context_merged_history_does_not_trust_local_main`
  (added post-security-review) proves a session log present only on local
  `main`, with no origin remote at all, still blocks; proven to discriminate
  by mutation. `test_branch_context_blocks_a_newer_log_that_is_not_upstream`
  and `test_branch_context_merged_history_exemption_needs_an_upstream` (both
  pre-existing, re-run to confirm no regression) still block a genuinely
  non-upstream newer log and a repo with no upstream ref at all.
- **Edge** (pre-existing, re-run to confirm no regression):
  `test_branch_context_survives_a_committed_merge_import` still requires the
  branch to own its own log before the exemption fires;
  `test_branch_context_fails_open_when_git_is_unavailable` still fails open
  when the `git` binary itself is missing.

## Push attempts and the base-branch merge

The first two push attempts failed the pre-push suite's `python-tests` job on
`tests/ci/test_validate_vendor_provenance.py::TestWorkflowContract::test_workflow_sets_up_uv`,
which asserted a stale `astral-sh/setup-uv` SHA pin. Confirmed this was not
caused by this branch: the test passed against `origin/main` directly, and
`git log 9e1ebd2..origin/main` showed exactly one new commit
(`a1ee96695`, PR #5219, merged after this branch's own start) that re-pinned
the same test to the current action SHA. Per the base-branch-recovered
playbook, merged `origin/main` (merge commit
`36bfb510b2858c5f22e164cd42342d04921a250a`, no conflicts) instead of patching
the test locally, re-ran the pin test and the branch-context suite to confirm
both still pass, and rebound `qaCommit` to the merge commit since it now
carries real, non-evidence-path changes (the ADR-096 and vendor-provenance
files from `origin/main`) after the prior `qaCommit`.

## Pre-existing findings, out of scope

`taste-lints` (advisory, non-blocking) flags `tests/test_lefthook_integration.py`
as exceeding 500 lines (11397 lines) and two functions exceeding complexity 10
(`test_configuration_uses_native_filters_scheduling_and_staging` at line 855,
`_functions_writing_one_path_two_ways` at line 6320). Both predate this change
and are unrelated to the branch-context tests added here; not addressed in this
PR.

## Status

QA COMPLETE.
