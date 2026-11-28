# Rerunning the original repros on main overturned six issue closures

**Atomicity**: 90%
**Category**: Issue triage
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E051. State checked on main at 1be533c496 (2026-11-26).

## Question

Can a closed issue's "fixed" claim be trusted without rerunning its repro on main?

## Conventional answer

Closed issues that carried a "fixed" claim were trusted as fixed.

## First-principles position

An agent ran one command per closure against origin/main. Eight closures held and six failed. Three failure shapes recur. An open PR was treated as a fix. A narrow claim closed a wider thread. A probe confirmed the code exists instead of varying the dimension the report named. A rerun on current main catches all three.

## Evidence with limits

- Audited 14 closed issues on origin/main at 95ecfc3e9, one command per closure (2026-08-05). 8 confirmed, 6 overturned and reopened.
- Issue 4561: the allocator run on two sibling branches chose session 9999 on both.
- Issue 4346: tracked source stayed mutated after an injected exception.
- Issue 4068: two forced failures returned exit 0.
- Shape one, an open PR treated as a fix: issues 3975 and 4068.
- Shape two, a narrow claim closing a wider thread: issues 4261, 4346 and 4210.
- Shape three, a probe that confirmed the code exists: issue 4561.
- Limits: One audit of 14 issues in one session on 2026-08-04 or 05. The transcript holds the summary table, not each command output. The full report sat in a scratch file that was not read.
- State on main at 1be533c496 (2026-11-26): no repo artifact. The memory patch drafted in that session (a triage-002 addendum) never reached main. Memories triage-001 and triage-004 exist but record other closure failures.

## Decision

Before closing an issue as fixed, require a merged PR whose merge commit is on origin/main. Then run the issue's own repro, varying the dimension the report names. Map every open criterion in the thread to a command and its output.

## Related

- `.serena/memories/pr-review/triage-001-verify-before-stale-closure.md`
- `.serena/memories/pr-review/triage-004-single-pass-close-verdicts-need-skeptic.md`
- `.serena/memories/session/session-number-collision-and-episode-rename.md`
