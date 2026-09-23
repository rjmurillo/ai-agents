# ADR Debate Log: ADR-086 Worktree Shim Amendment

## Summary

- **Rounds**: 1
- **Outcome**: Proposed amendment rejected
- **Final status**: ADR-086's decision stands. One sentence in its acceptance
  procedure is now stale; see "Open against ADR-086" below.

## Round 1 Summary

The proposed amendment added a repository-owned shim installer. Five reviewers
blocked it. One accepted only after major changes.

An exact two-worktree probe on Linux resolved the disputed premise:

- Native Lefthook wrote a branch-local absolute fallback into the shared shim.
- The configured `uv run --frozen lefthook` branch remained first and executed.
- Removing the installing worktree did not break a commit from the survivor.
- `lefthook check-install` failed only when another branch installed a different
  hook configuration.

The runtime worked. The checksum gate reported the false failure from issue
#4789.

### Platform scope of that probe

The probe ran on Linux. It does not generalize, and the resolution below is
split so that the part which does not generalize is not load-bearing.

`tests/test_lefthook_integration.py::test_install_resets_legacy_hooks_path`
records that Lefthook 2.1.10 generates a different shim on Windows from the
same `lefthook.yml`: the default template, resolving Lefthook through
`call_lefthook run` and omitting the configured `uv run --frozen lefthook`
runner. So the third bullet above, the branch order, is a Linux observation and
nothing more. No Windows probe was run, and none is claimed here.

What the fix rests on instead is `no_auto_install: true`. That is Lefthook
configuration read by the same binary on every platform, not shim template, and
`tests/test_lefthook_integration.py::test_a_sibling_worktree_run_does_not_rewrite_the_shared_hooks`
pins its effect: a sibling worktree whose config outruns the shared checksum no
longer re-syncs the shims and checksum that every other worktree reads.
`test_the_primary_hook_still_dispatches_after_a_sibling_install` drives the
reported install order and invokes the shared hook through a real `git commit`.

### The always-true branch, and issue #5431

The Linux shim's configured branch is `test -n "uv run --frozen lefthook"`,
which tests a non-empty string literal and is therefore unconditionally true.
Verified by reading the shim Lefthook installed into this repository.

Two consequences follow from that one line, and both are real:

- Every branch below it is unreachable, including the embedded absolute path.
  That is why a stale sibling path in the shared shim does not change what runs,
  which is this resolution's premise.
- Every documented fallback below it is also unreachable, so a clone where `uv`
  cannot resolve Lefthook has no path left. Issue #5431 records that as a defect
  and proposes giving the shim a reachable fallback.

These readings do not conflict; they are the same measurement. #5431 owns
changing the line. Nothing here should be read as closing it.

### Open against ADR-086

ADR-086's acceptance procedure still says a linked worktree "retains the
non-blocking warning documented under issue #2374, so it is not the acceptance
environment for this check." This branch deletes that leniency, because the
condition it forgave was a `check-install` checksum mismatch and the gate no
longer runs `check-install`.

Recording the replacement policy in ADR-086 is an accepted-record edit, which
`AGENTS.md` routes to `adr-review` and lists under "Ask First". It is left to
the issue owner rather than decided here. Two things to fix in the same pass:
the cited issue #2374 is about `pre_pr.py` blocking merge resolutions on
baseline failures and says nothing about Lefthook or worktrees, so that
citation is already wrong.

### Agent Positions

| Agent | Position |
| --- | --- |
| architect | Accept with changes |
| critic | Block |
| independent thinker | Block |
| security | Block |
| analyst | Block |
| high-level advisor | Block |

### Resolution

- Delete the proposed custom installer and shell parser.
- Keep Lefthook's native installer from ADR-086.
- Set `no_auto_install: true` to stop runtime checksum churn.
- Verify the configured Lefthook runtime instead of `check-install`.
- Make Git Hook Health real installation evidence. Executability alone is not:
  an executable `#!/bin/sh` plus `exit 0` runs no job, so the gate reads the
  installed `pre-push` and requires Lefthook's own dispatch line. Matching the
  installer's output is not the shell parser this debate rejected.

This resolution removes code instead of widening ADR-086's ownership boundary.
