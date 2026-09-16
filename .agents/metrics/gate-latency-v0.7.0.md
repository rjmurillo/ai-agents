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
2026-09-16, measured at commit `1251644dd` on branch
`claude/ai-agents-goal-spec-ch26ls`. `ci-scripts.md` MUST-16 records a job
measured at 6.83s standalone and 92.87s inside a real push on one machine on
one date, and says not to carry that ratio forward. The same restraint
applies to everything here: these figures establish the shape of the cost on
this box, not a planning number for another one.

Sample sizes are small: n=3 for pre-commit, n=2 for pre-push. No figure below
is labelled p95, because none of them supports one. The column that matters
is the worst observed run.

**The machine load at capture is not recorded, and that bounds every figure
below.** The sampler captures CPU count, platform, and Python version. It does
not capture load average, so no run here can be shown to have been taken on an
idle box or a busy one from this record alone. That omission matters precisely
because MUST-16's subject is the gap between the two: a latency figure carrying
no load reading cannot be compared against a later figure carrying a different
unknown load, and release gate 3 is a comparison. Issue #5318 item 1 asks for
the five named jobs to be measured "on a real push, per `ci-scripts.md`
MUST-16"; this record supplies the cost and not the load context that makes two
costs comparable. Repairing the instrument is the tracked follow-up.

Two reading notes for the per-run artifacts. A `group (N)` row is lefthook's
own total for a group, which is the sum of its members rather than wall clock,
so a parallel group routinely reports more seconds than the whole hook took
(`ci-scripts.md` MUST-17). Those rows are labelled `group total (sum)` in the
tables, and scheduling is read from `lefthook.yml`, never from that
arithmetic. Separately, pre-commit job counts move with the working tree,
because many pre-commit jobs gate on staged files: the markdown class ran 19
jobs here and 17 in an earlier capture of the same class on a cleaner tree, so
compare pre-commit figures only against a similarly staged tree.

## Headline

| Hook | Change class | n | Worst observed | Median | Jobs run | Declared budget |
|---|---|---|---|---|---|---|
| pre-commit | markdown | 3 | 9.82s | 9.66s | 19 | 6,230s |
| pre-commit | python | 3 | 7.22s | 7.22s | 17 | 6,230s |
| pre-push | markdown | 2 | 126.16s | 124.56s | 26 | 3,330s |
| pre-push | skills | 2 | 124.19s | 123.59s | 27 | 3,330s |
| pre-push | python | 2 | 124.11s | 124.00s | 28 | 3,330s |
| pre-push | hooks | 2 | 128.21s | 123.66s | 29 | 3,330s |

## What the numbers say

**The declared budget is not a latency, and the gap between them is
deliberate.** Pre-push declares 3,330 seconds and the worst observed run is
128.21 seconds, 26 times smaller. Pre-commit declares 6,230 seconds and the
worst observed run is 9.82 seconds, 634 times smaller. The declared figure is
the sum of per-job `timeout:` ceilings under lefthook's group semantics. It is
the number release gate 3 has been reading.

Read that gap as headroom the caps were given on purpose, not as slack to
reclaim. Two committed records already say why, and this measurement does not
overturn either:

- `ci-scripts.md` MUST-16: "Size a pre-push job's timeout for a loaded machine,
  not an idle one." A cap sized on an idle run is a cap a real push can exceed,
  "at which point a job that only reports is deciding whether code can ship."
- ADR-104, under "Neither target is enforced at runtime": "A hook that failed
  because the host was busy would replace a slow push with a refused one." The
  same record states what the declared sum is for: "the **declared** worst
  case, which is what a container actually has to survive."

The two figures answer different questions. The declared sum answers a
provisioning question, what the host has to survive in the worst case. The
measured figure answers a cost question, what a push takes when nothing is
contending. A ratio between answers to different questions is not an error to
correct.

**Nothing in this record is evidence for lowering a `timeout:`.** Every figure
here was taken on one box whose load at the time was not recorded, so none of
them bounds the same job under contention. Lowering a cap toward observed
latency trades a slow push for a killed job, and a killed job is a gate that
did not run: the job reports nothing, the push either fails for a reason
unrelated to the diff or proceeds with that gate silently skipped. Epic #5456's
non-goals rule out that trade by name, "weakening correctness or security to
reduce latency", and its gate 3 wording already treats ADR-104's 300s figure as
"a ceiling, not a goal". The direction this record can support is the opposite
one, and the next section takes it.

**Two jobs have little headroom, and they are the ones to watch.** Divide each
job's declared cap by its worst observed run across the four pre-push classes
above. The caps come from `lefthook.yml`; the observed figures come from the
per-job tables in `gate-latency-v0.7.0/`, so any reader can recompute this.

| Job | Declared cap | Worst observed | Cap over observed |
|---|---|---|---|
| `pre-pr-validation` | 4m (`lefthook.yml:570`) | 93.80s | 2.6x |
| `count-ratchets` | 90s (`lefthook.yml:491`) | 23.68s | 3.8x |
| `python-unreachable-statements` | 90s | 11.06s | 8.1x |
| `zero-collection-tests` | 4m | 18.71s | 12.8x |
| `path-normalization` | 90s | 3.57s | 25.2x |
| `python-tests` | 15m | 15.31s | 58.8x |

Every other pre-push job sits above 60x. The two at the top are the ones a
loaded machine can kill, and MUST-16 supplies the scale to judge that by: the
job it records went from 6.83s standalone to between 92.87s and 101.33s inside
a real push on that machine, a factor near 14. That figure is one machine on
one date and must not be carried forward as a multiplier, which is MUST-16's
own instruction. What survives is the shape: an in-push cost several times the
uncontended one is a thing that has been observed here before. At 2.6x,
`pre-pr-validation` does not have the room to absorb it, and it is a piped job,
so the jobs after it do not run when it dies.

This record does not propose a new cap for it. Choosing one needs a measurement
under load, which is the instrument gap named in the scope section above, and
`pre-pr-validation` is also the job issue #5318 item 1 leaves open with "then
decide per job". The finding here is narrower and stands on its own: if any
pre-push cap is wrong today, the evidence points at `pre-pr-validation` being
too low, not at any cap being too high.

**ADR-104's two targets both hold, on this box.** The 300s pre-push target is
met with the worst observed run at 43 percent of it. The 60s pre-commit
target, which ADR-104 itself calls a placeholder with no measurement behind
it, is met at 16 percent. ADR-104's re-evaluation trigger, "a real push
measures the pre-push hook above 300s", did not fire.

**Pre-push cost is concentrated in one job.** In the markdown class,
`pre-pr-validation` is 93.80s of the 126.16s total. `count-ratchets` is
23.68s, `zero-collection-tests` 18.31s, `python-tests` 15.20s. The
2026-08-19 record in `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`
had `python-tests` at 498.52s of 679s; that memory marked itself stale after
PR #5418, and this measurement replaces it. `python-tests` is 15.20s here and
is no longer the wall clock.

**Change class changes which jobs run**, which is the whole point of
measuring per class: 26 jobs for markdown, 27 for skills, 28 for python, 29
for hooks. The four glob-gated jobs #5318 item 1 names fire only for their
own class and skip otherwise with "no matching push files".

## Issue #5318 item 1: the five named jobs

| Job | Class that fires it | Worst observed |
|---|---|---|
| `security-scan` | every class, it declares no glob | 9.96s |
| `python-type-check` | `python`, and `hooks` (its file is a `.py`) | 0.52s |
| `plugin-load-e2e` | `skills` | 0.43s |
| `hook-anchoring-e2e` | `hooks` | 0.56s |
| `workflow-local-run` | `workflows` | not measured, see below |

Four of the five cost under a second when their glob fires, and
`security-scan` runs on every push for about 10 seconds. None is a tail risk
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
