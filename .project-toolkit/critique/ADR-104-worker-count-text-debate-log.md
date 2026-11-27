# ADR Debate Log: ADR-104 worker count text accuracy (2026-11-26)

Panel: reduced, architect and critic. The AGENTS.md trigger allows this panel for a prose-only edit. The amendment changes no decision, no executable enforcement, and no rule that other gates read.

Each seat ran as a read-only subagent on the sonnet model, using its agent definition. Seats received the ADR diff, the claims ledger, and the related source files. They did not receive the author's reasoning. The author consolidated the reports and made the fixes.

Claims ledger: `.project-toolkit/critique/ADR-104-worker-count-text-claims-ledger.md`. All four adr-generator exit gates recorded VERIFIED there before this debate opened.

Prior debate logs for ADR-104 stay closed: `ADR-104-debate-log.md`, `ADR-104-testmon-prepush-debate-log.md`, and `ADR-104-6200-pytest-step-bound-debate-log.md`.

## Summary

- **Rounds**: 2
- **Outcome**: Consensus. The architect accepted in round 1 and the critic accepted in round 2, with no P0 and no P1 open.
- **Final Status**: ADR-104 stays accepted (amended, text only).

## Decision under review

This amendment fixes text only. No decision changes. Three passages are corrected:

- The `testmon-seed` paragraph said the seed used the hook's worker cap. The seed pins a fixed cap of 4 and sets no CPU reserve.
- The 180s gap bullet said a 4 to 8 thread machine runs 4 workers. With the 3-CPU reserve, it runs 1 to 4.
- The Implementation Notes said `lefthook.yml` pins a cap of 4. Since PR #6364 and PR #6295 (both 2026-10-12), it sets `scaled` plus a reserve of 3.

## Round 1 Summary

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Accept | Decision unchanged and frontmatter valid. The Status note said "three passages" without naming them. The runner size rests on `ubuntu-latest`, with no source for the vCPU count |
| critic | Disagree-and-Commit | P1: the prose said workers are "the scaled cap less the reserve". The code is `max(1, min(cap, visible_cpus - reserve))`. P2: a hard-coded runner size, the cap below 4 CPUs left out, "the hook's own command" against the seed's own env, and the frontmatter date |

### Key Issues Addressed

- P1 formula wording. Both passages now say "the lesser of the scaled cap and the visible CPUs minus the reserve". The quoted counts were already right: 1 at 4 threads, 4 at 7 or 8, 16 at 48.
- The runner claim is now scoped to the 4-vCPU `ubuntu-latest` runner of run 38015601869.
- The scaled cap now says "never above the CPU count", which matches `min(clamped, visible_cpus)`.
- The seed paragraph now says "the hook's command" and states that its worker env is its own.
- The Status note now names the three passages.

### Not changed, with reason

- Frontmatter `date` stays 2026-11-26. adr-generator G3 defines `date` as last-updated, and Amend mode says to update it. The decision date stays in the `## Date` section.
- No test recomputes the ADR's numbers. It would call the same function the ADR describes and pin the output to itself. `tests/workflows/test_testmon_seed_job_build.py` pins the seed env instead.
- P2 line wrap in the seed paragraph. Markdown reflows it, so it renders as one paragraph.

## Round 2 Summary

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Not rerun | Accepted in round 1. The editor addressed both P2 items |
| critic | Accept | The formula matches `git_hook_policy.py:7913-7968`. The counts were recomputed by hand. The runner claim is scoped. No P0 or P1 remains |

## Outcome

Accepted. Both seats accept. The amendment changes text only, so a `git revert` restores the old text with no data or behavior at stake. It is a text correction with a named cause (PR #6364 and PR #6295, 2026-10-12), so the strategic lenses (Chesterton's Fence, path dependence, core vs context, second-system effect) do not apply.
