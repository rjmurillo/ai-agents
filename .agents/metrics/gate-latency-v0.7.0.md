---
type: metrics
id: gate-latency-v0.7.0
title: Measured local-gate latency for v0.7.0 release gate 3
epic: EPIC-5456
requirement: REQ-027
created: 2026-09-16
status: draft
---

# Measured local-gate latency, v0.7.0

Satisfies REQ-027 and answers issue #5318 items 1 and 2. Every figure below
was produced by `scripts/metrics/gate_latency.py` running the real hook, not
by summing `lefthook.yml` `timeout:` fields. The per-run artifacts in
`gate-latency-v0.7.0/` carry the full per-job tables and the exact command
that produced each one.

## Scope, stated before the numbers

One machine, one date. A 4-CPU Linux container, Python 3.14.7,
2026-09-16, measured at commit `610e14d31` on branch
`claude/ai-agents-goal-spec-ch26ls`. `ci-scripts.md` MUST-16 records a job
measured at 6.83s standalone and 92.87s inside a real push on one machine on
one date, and says not to carry that ratio forward. The same restraint
applies to everything here: these figures establish the shape of the cost on
this box, not a planning number for another one.

Sample sizes are small: n=3 for pre-commit, n=2 for pre-push. No figure below
is labelled p95, because none of them supports one. The column that matters
is the worst observed run.

## Headline

| Hook | Change class | n | Worst observed | Median | Jobs run | Declared budget |
|---|---|---|---|---|---|---|
| pre-commit | markdown | 3 | 3.77s | 3.74s | 17 | 6,230s |
| pre-commit | python | 3 | 7.24s | 7.09s | 17 | 6,230s |
| pre-push | markdown | 2 | 122.83s | 121.88s | 26 | 3,330s |
| pre-push | skills | 2 | 123.67s | 121.35s | 27 | 3,330s |
| pre-push | hooks | 2 | 123.92s | 121.79s | 29 | 3,330s |
| pre-push | python | 2 | 125.83s | 123.62s | 28 | 3,330s |

## What the numbers say

**The declared budget is not a latency.** Pre-push declares 3,330 seconds and
the worst observed run is 125.83 seconds, 26 times smaller. Pre-commit
declares 6,230 seconds and the worst observed run is 7.24 seconds, 860 times
smaller. The declared figure is the sum of per-job `timeout:` ceilings under
lefthook's group semantics, which is a worst case nothing has ever hit. It is
the number release gate 3 has been reading.

**ADR-104's two targets both hold, on this box.** The 300s pre-push target is
met with the worst observed run at 42 percent of it. The 60s pre-commit
target, which ADR-104 itself calls a placeholder with no measurement behind
it, is met at 12 percent. ADR-104's re-evaluation trigger, "a real push
measures the pre-push hook above 300s", did not fire.

**Pre-push cost is concentrated in one job.** In the markdown class,
`pre-pr-validation` is 91.20s of the 122.83s total. `count-ratchets` is
22.53s, `zero-collection-tests` 18.74s, `python-tests` 15.52s. The
2026-08-19 record in `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`
had `python-tests` at 498.52s of 679s; that memory marked itself stale after
PR #5418, and this measurement replaces it. `python-tests` is no longer the
wall clock.

**Change class changes which jobs run**, which is the whole point of
measuring per class: 26 jobs for markdown, 27 for skills, 28 for python, 29
for hooks. The four glob-gated jobs #5318 item 1 names fire only for their
own class and skip otherwise with "no matching push files".

## Issue #5318 item 1: the five named jobs

| Job | Class that fires it | Worst observed |
|---|---|---|
| `security-scan` | every class, it declares no glob | 7.12s |
| `python-type-check` | `python`, and `hooks` (its file is a `.py`) | 0.45s |
| `plugin-load-e2e` | `skills` | 0.41s |
| `hook-anchoring-e2e` | `hooks` | 0.53s |
| `workflow-local-run` | `workflows` | not measured, see below |

Four of the five cost under a second when their glob fires, and
`security-scan` runs on every push for about 7 seconds. None is a tail risk
on this box. That is worth stating plainly, because these five were named in
#5318 on the suspicion that they were the unmeasured tail, and on this
machine they are not: the cost is `pre-pr-validation`.

## Exclusions, named rather than left silent

- **`workflow-local-run` is not measured.** It runs `gh act`, which needs the
  `act` binary and a container runtime. Neither exists in this environment
  (`which act` finds nothing; `docker info` fails). Its 30m declared cap is
  the largest single contributor to the declared pre-push figure and remains
  entirely unmeasured. This is the one job of the five that #5318 item 1 asks
  about and this record cannot answer.
- **No paired measurement at the pinned baseline SHA.** See the next section.
- **p95 is not reported.** n=2 and n=3 cannot support a tail estimate.

## Gate 3: what this does and does not establish

Release gate 3 reads "Required local-gate p95 does not regress". Two pieces
of evidence, and they are not the same piece:

**Structural, and complete.** The hook job set at `origin/main` is the
baseline's set minus one job. Between `53ffe92c2` and `659097d6d`,
`lefthook.yml` changed by exactly one removed block, `retrospective-policy`
(2m, pre-push, removed by PR #5803). No job was added and no surviving job's
`timeout:` was raised, so the declared pre-push ceiling fell from 3,450s to
3,330s and the pre-commit ceiling is unchanged at 6,230s.

**Measured, and one-sided.** The figures above are HEAD only. A paired
capture at `53ffe92c2` was attempted in an external worktree on the same
machine and did not produce a comparable number: that tree is 50 commits
behind `main`, so its count ratchets evaluate against a base that has since
moved and the piped hook aborts after 9 jobs. Replaying an old SHA's gates
against a moving base is not a measurement this repository can take, and
saying so is more useful than a number that would not mean what it appears to
mean.

So the job-set diff bounds the declared ceiling, and it cannot bound
latency: 50 commits and 1,999 changed files separate the two SHAs, and test
files grew from 1,031 to 1,174. A surviving job can have slowed with no job
added. **Gate 3 is therefore recorded as a first measured reference, not as
met**, per REQ-027 AC-15. The comparison that would decide it is the next
release's measurement against this one, which is now possible and was not
before.

## Reproduce

Each artifact under `gate-latency-v0.7.0/` embeds the exact command that
produced it, with the repository path normalised. The JSON companion each
command writes is deliberately not committed: pretty-printed it runs 561 to
698 lines, over the taste-lint file-size ceiling, and the markdown carries
every figure this record cites. Re-run a command to regenerate it.
