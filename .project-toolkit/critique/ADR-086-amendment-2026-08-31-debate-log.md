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

## Closure of "Open against ADR-086" (issue #5490)

### Summary

- **Rounds**: 1
- **Outcome**: Consensus
- **Final status**: accepted (ADR-086 stays accepted; acceptance text amended)
- **Panel**: reduced, architect and critic.
- **Issue**: #5490. PR #5358 removed `check-install` from the gate.

### Panel basis

AGENTS.md picks the full panel only when the change touches executable
enforcement or a rule other gates read. This edit touches neither. The gate code
landed in PR #5358. This change makes the ADR prose match it. A search of
`scripts/`, `tests/`, `build/`, and `.github/` for `ADR-086-lefthook` found no
reader of the ADR body. The reduced panel applies.

Independence limit: the architect and critic passes ran in separate steps by the
authoring agent. They are not independent reviewers. The checks that do not
depend on the author are the gate source and the pre-PR run on the PR branch.

### Evidence verified

- `scripts/validation/checks_plugin.py` (`_lefthook_check_command`) returns
  `uv run --frozen lefthook version`. `validate_lefthook_installed` runs it from
  the repo root and its docstring forbids `check-install`.
- `scripts/validation/pre_pr_sequence.py` registers `Lefthook Installed` with
  the same rule and cites #4789.
- Issue #2374 owns the advisory style findings and the baseline failures in
  `pre_pr.py`. It is not a Lefthook or worktree issue. Every `#2374` hit in
  `scripts/` and `lefthook.yml` is about advisory style findings or accepted baselines.
- Issue #4789 is the checksum false failure this debate recorded above.
- `scripts/ci/verify_code_env.py` still runs `check-install` in CI setup. That
  is a separate CI step, not the local acceptance gate, and this edit does not
  change it.

### Key Issues Addressed

- Architect: the acceptance text prescribed a worktree exemption for a failure
  mode the gate no longer has. The amendment states what the gate runs and that
  a linked worktree is valid. It cites #4789.
- Architect: the "Run acceptance from the primary clone" sentence and the
  "primary-clone verification" phrase rested on the same exemption. Both now
  say the active checkout.
- Critic: removing only the #2374 sentence would leave `check-install` in the
  command block with no stated requirement. The command line was removed too.
- Critic: the amendment must not imply the shim is exercised by the gate. It
  states only that the gate runs `lefthook version`. The reason `check-install`
  is absent, its shared checksum, is stated once.

### Major Changes Made

- Confirmation intro: active checkout, primary clone or linked worktree.
- Confirmation block: `uv run --frozen lefthook check-install` removed.
- Acceptance paragraph: `Lefthook Installed` gate and linked worktree stated;
  the #2374 sentence removed.
- "primary-clone verification" reworded to "verification".
- Update History row added.

### Noticed, outside this amendment

- The acceptance paragraph still says Lefthook must report version 2.1.10.
  `pyproject.toml` pins `lefthook==2.1.17`. The 2026-10-11 debate log recorded
  the same drift for the other 2.1.10 mentions in the ADR.

### Agent Positions

| Agent | Position |
| --- | --- |
| architect | Accept. The text matches `checks_plugin.py` and `pre_pr_sequence.py`. |
| critic | Accept after changes. The command line removal and the primary-clone phrases were added. No open P0 or P1. |

### Next Steps

Owner review of the PR. No further rounds.
