---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14706-b57affd0a-fix-issue-4634-remove-inert.json
qaCommit: 08dff887792215b5589b8e324c8203d566a8288d
---

# Issue 4634 QA Report

## Verdict

PASS. One `push-ref-staleness` job remains, it reads the remote from a
placeholder lefthook actually expands, and parsed-config tests now reject a
duplicate job name in any hook.

## Scope

- Base: `bc179ad3a31f8d1c5265aaf22ccab8409a522de2`
- Head: `08dff887792215b5589b8e324c8203d566a8288d`
- Last code commit: `08dff887792215b5589b8e324c8203d566a8288d`
- Issue: #4634

## Reproduction

Same command, same repository, same environment. The stdin line claims the
remote holds `a225da30e1b7`; `origin/main` actually holds `bc179ad3a31f`, so a
working check must fail.

```text
uv run --frozen lefthook run pre-push --job push-ref-staleness --force \
  origin https://github.com/rjmurillo/ai-agents.git < pre-push-input.txt
```

Before (files from `origin/main`):

```text
summary: (done in 0.86 seconds)
✔️ push-ref-staleness (0.08 seconds)
🥊 push-ref-staleness (0.77 seconds)
```

Two executions under one name. The green line is the early job passing
`{remote}`: lefthook does not substitute that token, `git ls-remote "{remote}"`
resolves nothing, `_remote_sha` returns `None`, and `main` reads a missing
remote SHA as "new branch, no race". It reports success on every push.

After (head):

```text
[push-ref-staleness] Remote ref(s) advanced during this hook run.
  refs/heads/main: remote is at bc179ad3a31f, expected a225da30e1b7
exit status 3
summary: (done in 0.79 seconds)
🥊 push-ref-staleness (0.79 seconds)
```

One execution, correct detection, exit 3.

## Placeholder Evidence (level 1)

Enumerated from the pinned lefthook 2.1.10 binary that `uv` installs, not from
recall:

```text
strings .venv/lib/python3.14/site-packages/lefthook/bin/lefthook-linux-x86_64/lefthook \
  | grep -oE '\{[a-z_]*files\}' | sort -u
{all_files}
{files}
{push_files}
{staged_files}
```

Scratch-repo probes against the same binary confirmed: `{0}` expands to all
hook arguments, `{1}`..`{n}` expand to positional arguments, an absent
positional stays literal, and an unknown name such as `{remote}` is passed
through verbatim. A raw `.git/hooks/pre-push` shell hook confirmed the git
contract that makes `{1}` correct: `git push -u origin main` and a bare
`git push` both pass `ARGS=[origin ../up.git]`, and `git push ../up.git main`
passes `ARGS=[../up.git ../up.git]`. Argument 1 is always the remote name or a
URL that `git ls-remote` accepts.

## Checks

| Check | Result |
|---|---|
| `tests/ci/test_lefthook_config_integrity.py` (new) | 15 passed |
| `tests/test_push_ref_staleness.py` | 17 passed |
| `tests/test_lefthook_integration.py` runtime end-to-end | 837 passed (whole module, includes the new end-to-end test) |
| 11 lefthook, mutation, ratchet, and pushgate modules | 1120 passed, 2 skipped |
| `tests/mutation/test_mutate_lefthook_ratchet_wiring.py` | 5 passed on a clean tree |
| `uv run --frozen lefthook validate` | All good |
| `ruff check` on changed Python files | All checks passed |
| `scripts/validation/pre_pr.py` | See session log; run after session completion |

## Negative Controls

Every new test was proven to fail against the pre-fix tree, not merely to pass
against the fix.

| Control | Result |
|---|---|
| `_resolve_remote` reverted to `argv[0] if argv else "origin"` (the `origin/main` script) | 4 of 7 new unit tests fail: `test_blank_argument_falls_back_to_origin`, `test_unexpanded_positional_placeholder_is_a_configuration_error`, `test_unsupported_placeholder_is_a_configuration_error`, `test_placeholder_never_queries_a_remote` |
| Config tests run against `git show origin/main:lefthook.yml` | 4 of 15 fail: pre-push uniqueness, declared once, reads `{1}`, placeholder scan |
| End-to-end test run against pre-fix config and script | Fails; lefthook prints two green summary lines for a push it should block |

## Acceptance Evidence

Test names are copied from the files, not from recall.

- AC1, delete the inert duplicate: `lefthook.yml` declares `push-ref-staleness`
  once. `tests/ci/test_lefthook_config_integrity.py::TestPushRefStalenessJob::test_declared_exactly_once`
  counts the name across the pre-push jobs, groups included, and asserts the
  count is exactly 1, so the two-copy config fails it.
- AC2, keep one job that reads the remote from supported pre-push inputs: the
  retained job runs
  `uv run --frozen python scripts/validation/push_ref_staleness.py "{1}"` with
  `use_stdin: true`. Three tests pin the three inputs:
  `TestPushRefStalenessJob::test_reads_the_remote_from_the_first_hook_argument`
  (the run body contains `"{1}"` and not `{remote}`),
  `TestPushRefStalenessJob::test_reads_the_pushed_refs_from_stdin`
  (`use_stdin` is True), and
  `TestPlaceholderTokens::test_no_run_body_uses_an_unsupported_placeholder`
  (no run body anywhere in the config uses a token outside the enumerated set).
  `tests/test_lefthook_integration.py::test_pre_push_staleness_checks_the_remote_named_on_the_command_line`
  proves at runtime that the named remote reaches `git ls-remote`.
- AC3, parsed YAML test that rejects duplicate job names:
  `TestJobNamesAreUnique::test_hook_declares_each_job_name_once` parses
  `lefthook.yml`, walks nested groups while preserving duplicates, and asserts
  uniqueness per hook (parametrized over `commit-msg`, `pre-commit`,
  `pre-merge-commit`, `pre-push`). Three synthetic controls exercise the
  detector: it fires on a top-level duplicate
  (`test_detector_flags_a_top_level_duplicate`), fires on a duplicate nested
  inside a group (`test_detector_flags_a_duplicate_inside_a_group`), and stays
  silent when a top-level job and a nested job carry different names
  (`test_detector_accepts_distinct_names_across_nesting`). The placeholder scan
  carries the same pair: `TestPlaceholderTokens::test_detector_flags_the_reported_token`
  fires on `{remote}`, while `test_detector_accepts_supported_tokens` and
  `test_detector_ignores_shell_expansion` prove it does not over-fire.

## Inverse Failure Modes Closed

- Broadened detection without over-firing: the unsupported-placeholder scan
  allowlists only the tokens enumerated from the pinned binary, and it runs
  against the whole config. It passes on the current config and fails on
  `{remote}`.
- Guarded the mirror case in the script: if a positional placeholder is ever
  left unexpanded again (a bare `lefthook run pre-push` does exactly this),
  `_resolve_remote` prints the offending token on stderr and returns exit 2,
  the ADR-035 usage/configuration code. It does not substitute a default
  remote. Review of PR #4998 named the reason: comparing the pushed refs
  against a remote the caller never named exits 0 on a clean comparison nobody
  asked for, which is the original false green from the other side.
  `TestRemoteResolution::test_placeholder_never_queries_a_remote` asserts
  `_remote_sha` is never called, so the guard cannot degrade into the
  pass-everything behavior it replaces. Passing no argument at all still
  defaults to `origin`, which direct invocation for testing relies on
  (`test_missing_argument_falls_back_to_origin`).
- Ordering invariant preserved: `tests/test_mutation_workspace.py` asserts
  `mutation-safety` precedes `push-ref-staleness`. Keeping the early position
  and deleting the late copy keeps that assertion meaningful, and the module is
  green (18 passed).

## Review Round (PR #4998)

Three Copilot threads, each answered with a change rather than a reply alone.

| Thread | Finding | Resolution |
|---|---|---|
| Session log markdown lint evidence | "no changed markdown files" was wrong; the PR adds 4 | Replaced with the measured command and its verbatim output: `pre_pr.py --markdown-lint-only <4 paths>` reports `selected 0 of 4 target(s): each is excluded by .markdownlint-cli2.yaml`, rc 0. `.agents/**` and `.serena/**` are ignores entries at lines 138 and 139 |
| QA acceptance evidence cited tests that do not exist | `test_job_is_declared_once`, `test_reads_the_remote_from_a_positional_placeholder`, `test_does_not_use_the_unsupported_remote_token`, and a "same name in two hooks" control were invented, not read | Acceptance Evidence above now copies every name from the files. Verified with `pytest --collect-only` |
| `origin` fallback can hide a real staleness | Comparing against a remote the caller never named exits 0 on a clean comparison, recreating the false green | Adopted. A literal `{...}` argument now exits 2 (ADR-035 usage/configuration). The 3 unit tests that pinned the fallback were flipped in the same commit, and one now asserts `_remote_sha` is never called |

Re-run after the contract change: 62 focused tests pass
(`test_push_ref_staleness.py`, `test_lefthook_config_integrity.py`,
`test_lefthook_ratchet_wiring.py`, `test_mutation_workspace.py`), 837 pass in
`test_lefthook_integration.py`, `lefthook validate` reports All good, Ruff
clean. Before adopting the stricter contract, grep across the repository found
no `lefthook run pre-push` invocation against the real config in `scripts/`,
`tests/`, `.claude/`, `docs/`, or `.github/`, so no legitimate caller now
fails.

## Notes

The retained copy is the early one, so the diff deletes the block that happened
to work. That is deliberate: the script exists to abort before the 6 to 15
minute hook groups run, which only the early position achieves. The fix moves
the working argument onto the early job rather than the early position onto the
working job. The YAML comment and the commit body both state this.
