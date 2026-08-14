---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14706-b57affd0a-fix-issue-4634-remove-inert.json
qaCommit: 210e015a7c74fa79d8c6b4fa835d222f1cbcab93
---

# Issue 4634 QA Report

## Verdict

PASS. One `push-ref-staleness` job remains, it reads the remote from a
placeholder lefthook actually expands, and parsed-config tests now reject a
duplicate job name in any hook.

## Scope

- Base: `bc179ad3a31f8d1c5265aaf22ccab8409a522de2`
- Head: `210e015a7c74fa79d8c6b4fa835d222f1cbcab93`
- Last code commit: `259f78e64cf5ec22353cb0431e1ec903683e6dde`
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
| `tests/test_lefthook_integration.py` runtime end-to-end | 1 passed (module green) |
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
| `_resolve_remote` reverted to `argv[0] if argv else "origin"` | 4 of 7 new unit tests fail |
| Config tests run against `git show origin/main:lefthook.yml` | 4 of 15 fail: pre-push uniqueness, declared once, reads `{1}`, placeholder scan |
| End-to-end test run against pre-fix config and script | Fails; lefthook prints two green summary lines for a push it should block |

## Acceptance Evidence

- AC1, delete the inert duplicate: `lefthook.yml` declares `push-ref-staleness`
  once. `TestPushRefStalenessJob::test_job_is_declared_once` counts occurrences
  across groups and fails at two.
- AC2, keep one job that reads the remote from supported pre-push inputs: the
  retained job runs
  `uv run --frozen python scripts/validation/push_ref_staleness.py "{1}"`.
  `test_reads_the_remote_from_a_positional_placeholder` and
  `test_does_not_use_the_unsupported_remote_token` pin both halves, and the
  runtime test proves a named remote reaches `git ls-remote`.
- AC3, parsed YAML test that rejects duplicate job names:
  `TestJobNamesAreUnique` parses `lefthook.yml`, walks nested groups while
  preserving duplicates, and asserts uniqueness per hook. Three synthetic
  controls prove the detector fires on a duplicate, tolerates the same name in
  two different hooks, and sees duplicates nested inside a group.

## Inverse Failure Modes Closed

- Broadened detection without over-firing: the unsupported-placeholder scan
  allowlists only the tokens enumerated from the pinned binary, and it runs
  against the whole config. It passes on the current config and fails on
  `{remote}`.
- Guarded the mirror case in the script: if a positional placeholder is ever
  left unexpanded again (a bare `lefthook run pre-push` does exactly this),
  `_resolve_remote` warns on stderr and checks `origin` instead of treating the
  literal token as a remote name. `test_placeholder_fallback_still_reports_a_stale_remote`
  proves the fallback still returns exit 3, so the guard cannot degrade into
  the pass-everything behavior it replaces.
- Ordering invariant preserved: `tests/test_mutation_workspace.py` asserts
  `mutation-safety` precedes `push-ref-staleness`. Keeping the early position
  and deleting the late copy keeps that assertion meaningful, and the module is
  green (18 passed).

## Notes

The retained copy is the early one, so the diff deletes the block that happened
to work. That is deliberate: the script exists to abort before the 6 to 15
minute hook groups run, which only the early position achieves. The fix moves
the working argument onto the early job rather than the early position onto the
working job. The YAML comment and the commit body both state this.
