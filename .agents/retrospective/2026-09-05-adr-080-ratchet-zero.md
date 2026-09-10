# Retrospective: draining the ADR-080 model-pin ratchet to zero

**Date**: 2026-09-05
**Scope**: Issue #5605, PR #5607, branch `claude/adr-80-ratchet-zero-99zo5x`
**Failure mode classification**: #10, Silent defaults and guard-clause suppression
(`.agents/governance/FAILURE-MODES.md:26`). A near-miss, caught in review before
it shipped. Secondary touch on #4, False completion markers: the first draft of
the ADR section claimed the ratchet was at zero without saying that the gate
reads five globs and not the repository.

## What happened

The baseline at `scripts/validation/model_pin_baseline.json` had held 45
grandfathered pins since 2026-07 against ADR-080 rule 6's obligation to shrink
it each release. 37 of them were bare `sonnet` or `opus` aliases that rule 3 can
never justify, so removal was the only reachable end state. The mechanical work
was clean: 22 commits, every one within the five-authored-file atomic limit, and
`check_model_pins.py --mode enforce` green at each stage.

The review found two defects the mechanical work could not have surfaced.

## Impact

| Area | Severity | Effect |
|---|---|---|
| Governance gate integrity | High | `--update-baseline` would have silently re-armed the drained ratchet |
| Gate coverage | Medium | Two hand-authored trees had never been scanned; one held a retired model id |
| Decision record accuracy | Medium | The first draft cited evidence measured on a different pin shape |

## Root cause, five whys

**Defect 1: the drain disabled the guard that protected it.**

1. Why would `--update-baseline` re-arm the ratchet? Because `write_baseline`
   set `frozen_count` from the tree whenever the stored count was zero.
2. Why did that read as "no baseline yet"? Because zero had only ever meant
   "file absent"; a real baseline always carried a positive count.
3. Why did nobody notice? Because the branch was unreachable. Before this
   change no baseline in this repository's history had ever been at zero.
4. Why did the growth guard in `run_check` not catch it? Because entries and
   ceiling moved together, so the comparison could not fire.
5. Why was there no test? Because the terminal state of a draining ratchet had
   never been reached, so nobody had a reason to pin it.

Root cause: **draining a ratchet to its terminal value moves the code into a
branch that was dead for the whole life of the feature.** The last step of a
burn-down is the first execution of its own edge case.

**Defect 2: the scope claim outran the scanner.**

The ADR text said every pin on disk passes. `_UNIT_GLOBS` reads five trees.
`src/claude/*.md` (hand-maintained, not generated) and `.github/prompts/*.md`
were not among them, and the second held `model: Claude Opus 4.5 (copilot)` on
two files: a retired id, the exact class that broke CI in issue #2839 and
motivated ADR-080. The gate written to catch that class had never looked in that
directory.

## What went well

- **The six-agent adr-review debate earned its cost.** Two agents returned
  Block, independently, on two different defects. The security agent found the
  `write_baseline` re-arm; the independent-thinker found that the migration
  cited amendment finding 1, which measured a versioned id on Copilot CLI, as
  justification for removing bare aliases the same amendment says were never
  probed. Neither is visible from a green gate.
- **Negative controls did their job.** Every new test was run against the old
  code. Four of seven fail without the fix, which is the difference between a
  test and a comment.
- **The prior migration's memory paid off.** `.serena/memories/tasks/issue-2840-model-pin-migration.md`
  named both blockers that had stopped the agent half in 2026-07 and named the
  scope gate as the trap. That saved rediscovering all three.

## What to improve

- **A ratchet's terminal value needs a test the day the ratchet is written**,
  not the day it is reached. Defect 1 is a general shape, not specific to this
  gate: every count ratchet under `scripts/ci/` has a zero it has never seen.
- **A gate's glob list is part of its claim.** Any statement that "the tree is
  clean" has to name the scope the scanner actually reads, or it is a claim
  about something nobody measured.
- **Evidence citations degrade quietly across amendment revisions.** Finding 1
  was measured on one pin shape and one harness; it read as general support for
  any pin removal. The commit bodies on this branch carry that overreach, and
  the correction lives in the ADR rather than in rewritten history.

## Remediation

| Action | Where | Status |
|---|---|---|
| Key `write_baseline`'s first-write branch on file existence; refuse a rise | `scripts/validation/check_model_pins.py` | Done, PR #5607 |
| Record only failing pins in the baseline | `scripts/validation/check_model_pins.py` | Done, PR #5607 |
| Scan `src/claude` and `.github/prompts` | `scripts/validation/check_model_pins.py` | Done, PR #5607 |
| Remove the two retired `Claude Opus 4.5 (copilot)` pins | `.github/prompts/` | Done, PR #5607 |
| Seven tests, terminal state and scope, with negative controls | `tests/validation/test_check_model_pins.py` | Done, PR #5607 |
| Withdraw the finding-1 citation; scope the passing claim | ADR-080 Migration 2026-09-05 | Done, PR #5607 |
| Decide the skill-copier half of amendment finding 4 | Issue #5606 | Open, owner |
| Audit the other count ratchets for the same terminal-value branch | Not filed | Open, no owner |

## Evidence

- Issue #5605, issue #5606, PR #5607.
- Debate log: `.agents/critique/ADR-080-ratchet-zero-debate-log.md`, six agents,
  two rounds, one Disagree-and-Commit dissent recorded.
- ADR-080, section "Migration 2026-09-05: the ratchet reached zero".
- Prior migration: issue #2840, and the Serena memory this session corrected.
- The retirement break this gate exists to prevent: issue #2839.
