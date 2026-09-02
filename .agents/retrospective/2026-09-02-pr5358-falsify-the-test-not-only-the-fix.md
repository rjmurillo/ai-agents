# Retrospective: PR #5358, falsify the test and not only the fix

## Session Info

- **Date**: 2026-09-02
- **Agent**: Claude Code, driving PR #5358 on branch `claude/fix-4789-isolate-lefthook-installs-across-worktrees`
- **Task Type**: Review-round remediation on Lefthook worktree isolation. Round 4.
- **Outcome**: Five review findings closed, one regression test caught passing against its own absence, one jointly fail-open gate pair fixed, one architecture item halted at the Ask First boundary.

## Phase 1: Insights Generated

### Finding 1: A test that passes is not yet evidence, even when the fix is real

The review asked for a two-worktree regression test pinning `no_auto_install: true`.
I wrote one from a model of how Lefthook re-syncs, ran it, and it passed. Then I ran
it with `no_auto_install` deleted from `lefthook.yml`, and it passed again.

The test proved nothing. The fix was real; the test did not reach it.

The model was wrong in one detail. Lefthook re-syncs the shared shims when the active
worktree's config mtime is newer than the timestamp stored in
`<common git dir>/info/lefthook.checksum`. My fixture wrote the sibling config in the
same wall-clock second as the install, so the mtime was not newer and no sync was ever
attempted. Pushing the mtime forward with `os.utime` made the sync fire, and the test
then failed without the fix and passed with it.

**Root cause**: the falsification run and the passing run answer different questions.
The passing run asks whether the code works. The falsification run asks whether the
test can see it. Only the second one was capable of catching this, and it is the one
that is easy to skip once the first comes back green.

The generalization is not "run tests twice." It is that a new regression test carries
the same burden as a reported defect: it is a hypothesis until measured against the
state it claims to detect.

### Finding 2: Two gates, each defensible alone, fail open as a pair

This branch replaced `lefthook check-install` in the `Lefthook Installed` gate with
`uv run --frozen lefthook version`. That was correct on its own terms: `check-install`
compares one checksum shared by every linked worktree, so it fails in a sibling whose
hooks are fine, which is the false failure issue #4789 reported.

The docstring justifying it named the adjacent `Git Hook Health` gate as the thing that
still proves installation. `Git Hook Health` accepted any executable `pre-push`. Its own
fixture wrote `#!/bin/sh` and `exit 0`.

So a clone whose hook dispatched nothing passed both gates. Neither gate was wrong in
isolation. The pair had no member that read the hook.

**Root cause**: each gate's docstring described what the other one covered, and no one
checked that claim against the other file. Leaning on an adjacent gate is a citation,
and a citation to behavior needs the same verification as a citation to a line.

Worth noting where the fixture came from: the inert `exit 0` stub was written to make
the healthy-path assertions pass, so every positive test in that file was satisfied by
exactly the state the gate exists to refuse. A fixture chosen for convenience became the
proof that the gate did nothing.

### Finding 3: One measurement, two conclusions, and neither was wrong

The generated shim's configured branch is `test -n "uv run --frozen lefthook"`, which
tests a non-empty string literal and is therefore unconditionally true.

This PR read that as the reason a stale sibling path in the shared shim cannot change
what runs, because every branch below it is unreachable. Issue #5431 read the same line
as a defect, because every documented fallback below it is also unreachable, so a clone
where `uv` cannot resolve Lefthook has no path left.

Both readings are correct and they are the same measurement. The reflex was to decide
which one to adopt. The right move was to record both consequences, say which issue owns
changing the line, and stop claiming the other one's territory.

### Finding 4: A probe on one platform is a probe on one platform

The ADR-086 amendment debate rested on a two-worktree probe stating that the configured
runner branch was first and executed. The probe ran on Linux. This repository's own
integration test already documented that Lefthook generates a different shim on Windows
from the same config, omitting that runner entirely.

The repair was not to run a Windows probe, which this session could not do. It was to
split the resolution so the Linux-only observation is not load-bearing: what the fix
rests on is `no_auto_install`, which is configuration read by the same binary everywhere,
now pinned by a test. The branch-order result stays recorded as a Linux observation.

An unverifiable premise does not have to be verified before shipping. It has to stop
carrying weight, or the work stops.

## Failure Mode Classification

Against `.agents/governance/FAILURE-MODES.md`. No new class proposed; all four
findings land in existing ones.

| Finding | Class | Severity | Why |
|---|---|---|---|
| 1. Regression test passed with and without the fix | 4, False completion markers | High | The test reported coverage it did not have. It would have merged as evidence for AC-3 while pinning nothing. |
| 1. Mechanism asserted before measurement | 9, Confident-incorrectness recurrence | High | The mtime trigger was modeled from memory, not read. |
| 2. Two gates jointly fail-open | 10, Silent defaults and guard-clause suppression | High | Each gate's docstring cited the other as covering the difference; neither read the hook. The `exit 0` fixture made every positive assertion vacuous. |
| 4. Linux probe stated as general | 9, Confident-incorrectness recurrence | High | A single-platform result was written as a platform-independent conclusion. |
| 5. "Not load-sensitive" posted to #5441 | 9, Confident-incorrectness recurrence | High | A profiling harness that was itself the dominant load; load rose 4.84 to 15.02 during the run and I recorded both numbers without drawing the inference. Retracted in the same thread. |

Class 9 accounts for three of five. The common shape is not carelessness about
evidence, it is drawing a general conclusion from a measurement whose scope was
narrower than the claim. Each time the scope was visible in my own output.

## Remediation

| Action | Owner or issue |
|---|---|
| Make the pre-push ratchet budget hold under concurrent agent sessions, with the acceptance criterion that the fix must not assume a retry succeeds | Issue #5441, PR #5466 |
| Stop `Refs #n` disarming the required `Validate Spec Coverage` judge, which `.claude/rules/universal.md` MUST-3 mandates for unsupported claims | Issue #5489, filed from this session |
| Record the replacement linked-worktree policy in ADR-086 and correct its wrong #2374 citation. Accepted-record edit, so `adr-review` plus the Ask First boundary | Unassigned. Needs the issue owner for #4789; the exact sentence is named in `.agents/critique/ADR-086-amendment-2026-08-31-debate-log.md` |
| Decide whether AC-1 of issue #4789 is amended to the reachability wording or stays unmet | Issue #4789, proposal posted 2026-09-02 |
| Windows two-worktree probe with the uv runtime present and the `PATH` binary absent | Unassigned. Stated as an uncovered gap in the `validate_lefthook_installed` docstring |

## Phase 2: What To Keep

- Falsify every new regression test against the absence of the thing it pins, before
  committing it. Cheap, and it is the only step that catches a test aimed at the wrong
  mechanism.
- When a gate's rationale cites an adjacent gate, open the adjacent gate and read what
  it actually accepts.
- When a finding and your own position rest on the same measurement, reconcile them in
  writing rather than choosing.
- Before publishing a measurement, check whether the act of measuring changed the thing
  measured. The load numbers were in my own output on both sides of the run.

## Phase 3: What Changed

- `tests/test_lefthook_integration.py`: two two-worktree cases, one pinning
  `no_auto_install`, one driving the reported install order through a real `git commit`.
- `scripts/validation/check_git_hook_health.py`: reads the installed `pre-push` and
  requires Lefthook's own dispatch line; its test fixture no longer writes an inert stub.
- `CONTRIBUTING.md` and the gate ladder: name the two gates that replaced `check-install`.
- `.agents/critique/ADR-086-amendment-2026-08-31-debate-log.md`: platform scope, the
  #5431 reconciliation, and the ADR-086 acceptance-procedure sentence left to the owner.

## Phase 4: Left Open

Recording the replacement linked-worktree policy in ADR-086 is an accepted-record edit.
`AGENTS.md` routes any `ADR-*.md` edit to `adr-review` and lists architecture under
Ask First, so this session halted that branch rather than guessing. The exact stale
sentence, and the wrong issue citation inside it, are named in the debate log.
