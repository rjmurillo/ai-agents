# Decision: retired plans go to .agents/archive/plans/, not .agents/plans/completed/

## Question

Where does a finished execution plan go when it leaves `.agents/plans/active/`?

## Conventional answer

`.agents/plans/README.md` and `.claude/skills/execution-plans/SKILL.md` both
say `completed/` (successfully finished) or `abandoned/` (stopped with
rationale). The skill exposes `complete plan` and `abandon plan` triggers that
move the file there.

## First-principles position

The documented lifecycle had never once been used. On 2026-07-26 the repo held
13 plans in `active/`, created 2026-04-11 through 2026-05-10, every one marked
`Status: In Progress`, with `completed/` and `abandoned/` both empty. Meanwhile
`.agents/archive/` already held retired plans from earlier eras:
`plan-pr760-fixes.md`, `pr43-remediation-plan.md`, `pr830-remediation-plan.md`,
and four `pr-60-*` plan and review documents.

The archive, not `completed/`, is where this repository has actually put
retired plans for its whole history. The user confirmed it directly:
"we haven't deleted anything previously. so don't do that. instead, move to
.agents/archive/".

## Evidence

- `.agents/archive/plans/` now holds all 13 plans plus a `README.md` recording
  the per-plan verdict and the evidence behind each one.
- Verification bar used: a closed tracking issue was not sufficient. Each plan
  also needed its named deliverable present in the working tree. Two plans
  passed the issue check but revealed drift on the disk check.

## Decision

Retire plans to `.agents/archive/plans/`. Preserve the file; never delete it.
Leave the stale `Status: In Progress` header intact so the archive matches what
shipped, and carry the real verdict in the archive README instead.

Root cause of the backlog is tracked in issue #3426: nothing invokes the
closeout triggers, so `active/` refills. Two residual defects found during the
pass are tracked in #3424 (bundle registry 15/15 stale) and #3425 (orphan
`.claude/review-axes/` references).

## Gotcha for the next reader

Plan filenames encode REQ numbers that were later reassigned.
`req-008-m1-skill-contracts.md` is not REQ-008 (that is
`review-axes-convergence`); the gate it documents shipped as REQ-017. Two
session logs and one script comment still cite plan paths that never existed:
`req-009-retro-fixes-pr-1965.md` and `req-008-step-0-5-memory-first-gate.md`.
Do not trust a plan filename as a spec pointer.
