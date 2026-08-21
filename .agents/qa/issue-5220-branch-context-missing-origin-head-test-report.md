---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-5220-session-log-false-positive.json
qaCommit: b3c0d7f12c6f770807e2f535ecafc5d5d87707a5
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
| `uv run --frozen python -m pytest tests/test_lefthook_integration.py -k "branch_context" -q` | 23 passed |
| `uv run --frozen python -m pytest tests/test_lefthook_integration.py tests/test_validate_session_json.py -q` | 1239 passed, 1 skipped |
| `uv run --frozen ruff check scripts/validation/git_hook_policy.py tests/test_lefthook_integration.py` | All checks passed |
| `uv run --frozen mypy scripts/validation/git_hook_policy.py` | Success: no issues found in 1 source file |
| `uv run --frozen python scripts/validation/pre_pr.py` | 57 passed, 0 failed, 0 skipped; re-run against the final tree after the SEC-001 fix |
| `uv run --frozen python scripts/validation/git_hook_policy.py taste scripts/validation/git_hook_policy.py` | `taste-lints: 1 files scanned, no violations found` (post complexity-extraction fix) |
| Mutation check: reintroduce the local-`main` rung, re-run the new negative test | Fails (`assert 0 == 1`), confirming the test discriminates; reverted and re-confirmed byte-identical to the source file |
| `AI_AGENTS_PYTEST_WORKER_CAP=4 uv run --frozen python scripts/validation/git_hook_policy.py pytest` (full suite, matches the pre-push job exactly) | 27659 passed, 73 skipped + 24 passed + 46 passed, 9 deselected + 30 passed, across zero errors on a clean tree |

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

## Second push attempt and a second base-branch merge

A subsequent push's `Python Security Checks` CI job failed on a newly
disclosed `pip-audit` finding, `PYSEC-2026-3721` in the pinned `pip==26.1.2`,
unrelated to this PR's diff. Confirmed via `mcp__github__actions_list`
(`list_workflow_runs` for `pytest.yml` on `main`) that `main`'s own most
recent run at the time (`ce4860ea60`) had already fixed this: PR #5225,
"fix(ci): bump audited pip pin to 26.2 for PYSEC-2026-3721", merged to `main`
after this branch's prior merge point. Merged `origin/main` again (merge
commit `f170c11c6013cf565a5e3d553b313e9c8f1240c5`, no conflicts) rather than
patching the pin locally, and rebound `qaCommit` to it for the same
staleness reason as the first merge.

## Automated PR review findings, addressed

The `Validate Spec Coverage` check returned PARTIAL on the PR as first opened,
correctly identifying two real gaps by direct code reading (not surface
pattern-matching):

- Issue #5220's second proposed fix ("say which precondition failed") was
  unimplemented. `check_branch_context` now distinguishes "branch owns a log
  but no upstream ref resolves at all" from ordinary co-mingling, naming
  `git remote set-head origin --auto` only in the former case. New tests:
  `test_branch_context_merged_history_exemption_needs_an_upstream` (extended
  with a `capsys` assertion) and
  `test_branch_context_message_stays_generic_without_an_owned_log`.
- `_read_upstream_default_blob` (a pre-existing, unrelated call site) carried
  its own duplicate `origin/HEAD` → `origin/main` fallback with looser
  existence-checking than the new resolver, and neither cited the other.
  Consolidated onto one shared `_resolve_upstream_default`, which also renamed
  from `_merged_history_upstream` since it now serves two call sites.

The message-selection branch added for the first finding pushed
`check_branch_context` to cyclomatic complexity 11 (repo ceiling 10, caught by
`taste-lints`, self-inflicted). Extracted `_print_branch_context_mismatch` to
hold it back at 10; no behavior change, re-confirmed by the full branch-context
suite.

The `Validate PR` check separately flagged the PR description as not matching
the diff; the description was rewritten to reflect the consolidation and
message-improvement commits once they landed, rather than describing only the
original two-rung fix.

## A confirmed-flaky, unrelated local test

A `python-tests` pre-push run failed exactly one test:
`tests/test_pr_autofix_late_live_state_gate.py::test_fast_exit_reports_lease_loss_after_wait[src/copilot-cli/skills/pr-autofix/SKILL.md]`,
asserting on a race-sensitive lease-renewal message
(`LEASE_RENEWAL_INTERVAL_SECONDS=0.05` in the test fixture) under the full
parallel pre-push job group's resource contention. This file is untouched by
this PR. Confirmed as a pre-existing flake, not a regression: a standalone
`AI_AGENTS_PYTEST_WORKER_CAP=4 uv run --frozen python scripts/validation/git_hook_policy.py pytest`
run against the identical clean tree, immediately before the failing push,
passed both parametrizations of that exact test along with all 27,659 other
collected tests. Per `.claude/rules/testing.md`'s flake-handling guidance this
was the one confirmatory re-run; the push was retried rather than the test
suite widened.

## Pre-existing findings, out of scope

`taste-lints` (advisory, non-blocking) flags `tests/test_lefthook_integration.py`
as exceeding 500 lines (11397 lines) and two functions exceeding complexity 10
(`test_configuration_uses_native_filters_scheduling_and_staging` at line 855,
`_functions_writing_one_path_two_ways` at line 6320). Both predate this change
and are unrelated to the branch-context tests added here; not addressed in this
PR.

## Superseded by 746e2c36a (PR #5229, issue #5228)

After this QA report reached PASS, a subsequent `origin/main` fetch surfaced
commit `746e2c36a` ("docs: discontinue session log file creation", PR #5229,
issue #5228), which rewrote `_is_merged_history` and `check_branch_context` in
`scripts/validation/git_hook_policy.py` more completely than this branch: it
routes `_is_merged_history` through the pre-existing `_read_upstream_default_blob`,
which already carried an `origin/HEAD` -> `origin/main` fallback before this
branch or issue #5220 existed, and it drops the "current branch owns a
same-day log" precondition entirely, since session log creation is now
discontinued (`.claude/rules/session-logs.md` MUST 1) and that precondition
can never be satisfied again.

Verified empirically against `origin/main` at `746e2c36a` in an external
worktree: reproduced issue #5220's exact scenario (fresh clone-shape repo,
`origin/HEAD` unresolved, a same-day log from another branch imported by
merge, current branch owning its own log). `check_branch_context` returned
`0` (pass); the pre-fix code returns `1` (block).

PR #5226 was closed unmerged as superseded; issue #5220 was closed as
completed, both citing this evidence. This branch then merged `origin/main`
and took its version of `scripts/validation/git_hook_policy.py` and
`tests/test_lefthook_integration.py` entirely (`git checkout --theirs`); the
post-merge diff against `origin/main` for both files is empty.

## Status

QA COMPLETE. Superseded: see above. No code from this branch merged to `main`.
