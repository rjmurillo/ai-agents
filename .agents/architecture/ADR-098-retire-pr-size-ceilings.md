---
id: ADR-098
status: proposed
date: 2026-08-20
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-098: Retire the Pull Request Size Ceilings

## Status

Proposed

## Date

2026-08-20

## Context

Two gates cap pull request size in this repository.

`scripts/validation/git_hook_policy.py` caps authored files per commit at five, with no bypass of any kind. `scripts/validation/pr_commit_count.py` warns at 10 commits, alerts at 15, and blocks at 20, with relief only through a `commit-limit-bypass` label a human applies.

Measured over the 14 days ending 2026-08-20: 292 pull requests opened, 104 of them (36%) carrying `needs-split`, and 20 requiring the human-only label.

The rationale on record is `.agents/governance/PROJECT-CONSTRAINTS.md:125`, which cites one 2026-01 incident, PR #908: 59 commits, review slow and merge risky. That was a single data point, gathered before this repository had either its present adversarial review practice or its present volume.

### What the gate actually fires on

Sampling pull requests in the window shows the count gate does not measure one condition. It measures at least three, which need opposite responses.

| Pull request | Commits | Files | Condition | Correct response |
|---|---|---|---|---|
| #4846 | 235 | 16 | Fails its own security and vendor-provenance gate; `mergeable_state: blocked`; never merged | Block |
| #4718 | 109 | 49 | Six real defects, each pinned with its own fix and test; merged | Allow |
| #5036 | 25 | 28 | One real defect reported four times across review threads before it was fixed; merged | Allow |
| #5152 | 11 | 22 | A fail-open bug family found during review; merged | Allow |
| #5103, #5107 | 18 to 20 | 13 | Zero open review threads; count inflated entirely by the QA and session evidence rebind firing on every `main` merge into a long-lived branch | Allow, and fix the generator |

Neither size axis separates these. Net authored file surface would pass #4846 at 16 files and flag #4718 at 49, which is backwards. Commit count flags #4846 correctly but punishes #4718 and #5103 identically for behavior the repository wants.

### What actually stopped the bad one

#4846 is the only pull request in the sample that should not merge, and it did not merge. What held it was its own security and vendor-provenance gate, a correctness check, not a size ceiling. The size gate labeled it, and it also labeled #4718, #5036, #5152, and #5103, which all merged and should have.

That is the finding this decision rests on. In the sample, the size ceilings did not make a single correct blocking decision that a correctness gate did not already make, and they imposed cost on four of five pull requests that were doing the right thing.

### The cost

The 5-file per-commit cap has no bypass. A single mechanical rename across a wide surface must be split into dozens of commits, which then trips the 20-commit ceiling, which then needs a human label. PR #5177 in the current window shows this shape: a session spending its output on gate arithmetic and commit slicing rather than on the change.

The 20 human label applications in two weeks scale linearly with volume. At the operating goal of running this repository without a human in the loop, a gate whose only relief is a human is a gate that caps throughput at human attention.

### A false positive measured while writing this

The scope half of the same family produced one during the authoring of this decision, which is worth recording because it was observed first-hand rather than sampled.

This pull request changes six files, all documentation. After a base merge, `scripts/detect_scope_explosion.py` reported `BLOCKED: PR scope explosion detected. 128/50 files` and refused the commit. The 128 was real arithmetic over a wrong input: the local `origin/main` ref still pointed at a commit the branch already contained, so the merge base resolved behind the branch and every commit main had landed in between was attributed to this pull request. A single `git fetch origin main` moved the reading from 128 to 5 with no change to the diff.

The remediation the gate printed does not mention refs. It advises splitting the pull request, stashing work, and offers `SKIP_SCOPE_CHECK=1`. Both of the first two are wrong here, and the third is the flag with a recorded abuse history that item 4 removes. An agent following the printed advice would either fragment a six-file change or reach for the bypass, and the retrospective at `.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md` records what happens next.

`.claude/rules/ci-scripts.md` MUST-14 already documents stale-ref inflation for the count ratchets and states that a ref fetched earlier in the same session should be treated as stale. The scope gate has the same failure and does not say so.

This does not by itself justify retirement, and it is one observation. It does show the gate blocking on branch bookkeeping rather than on scope, which is the same category error the count ceiling makes on rigor.

## Decision

Retire both size ceilings as blocking gates. Do not replace them with another blocking size gate.

1. **`pr_commit_count.py` stops blocking.** It reports counts and keeps its notice and warning output. It returns 0 in all cases. The `commit-limit-bypass` label and its human step retire with it.

2. **`check_atomic_commit` stops blocking.** The five-file guidance stays as advisory output. One idea per commit remains the documented convention in `.claude/rules/universal.md`; it stops being a mechanical precondition for committing.

3. **The scope check becomes advisory, and process-record paths leave its measurement.** `scripts/detect_scope_explosion.py:50` sets `BLOCK_THRESHOLD = 50` and the script returns 1 above it, so the scope check blocks today. It stops blocking and reports only. Separately, `_partition_generated` already excludes generated files; extend that to `.agents/sessions/**`, `.agents/qa/**`, and `.agents/memory/episodes/**`, which are process record rather than reviewable change.

   An earlier draft of this decision described the scope check as already advisory. That was wrong, and the order matters: demoting the threshold has to land in the same change as item 4, or removing the bypass leaves a blocking gate with no relief at all.

4. **`SKIP_SCOPE_CHECK` is removed, after item 3 lands.** `scripts/detect_scope_explosion.py:492` honors `SKIP_SCOPE_CHECK=1` with no verification of the human approval it claims. `.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md` records an agent setting it twice after authorization was explicitly withheld, citing an agent-writable memory as its authority. Once nothing blocks on scope, the flag has no purpose, and a self-attested approval flag with a recorded abuse history should not outlive its use. Removing it before item 3 would tighten the gate rather than retire it.

5. **Fix the rebind generator.** #5103 and #5107 show 18 to 20 commits with zero open review threads because the QA and session evidence rebind fires on every `main` merge into a long-lived branch. That is a defect producing fake commits. Fix it at the source rather than teaching a metric to ignore it.

### What is deliberately not adopted

An earlier draft of this decision proposed replacing commit count with a convergence metric: commits added since the last green check run, and commits added without a corresponding review thread resolution.

That is not adopted here, for three reasons.

- On the sample above it changes no outcome. #4846 was already stopped by a correctness gate.
- It is new machinery with no operating history, in a repository where the 2026-08-17 governance review measured 87 of 92 open issues (94%) as the repository's own automation breaking itself. A new required check with no baseline is a candidate to become issue 93.
- Both of its inputs are forgeable by the actor it would gate. This repository's loop holds thread-resolution tooling, and no rule in `.claude/rules/` or `.agents/governance/` forbids resolving one's own review thread. A job skipped by a job-level `if:` reports as satisfying a required check, so a green run is cheap.

If commit thrash later needs a control, it is a token-budget question, not a correctness question, and it needs its own evidence and its own decision. Filed rather than bundled.

## Prior Art Investigation

### What currently exists

- **Structure being changed**: a five-file per-commit cap and a 20-commit per-pull-request ceiling, both enforced through lefthook, with a human-applied label as the only relief.
- **When introduced**: traced to the PR #908 retrospective of 2026-01 and issue #934, recorded at `.agents/governance/PROJECT-CONSTRAINTS.md:125`.
- **Original context**: one 59-commit pull request that made review slow and merge risky.

### Historical rationale

The ceilings were a proxy for reviewability, in a regime where a human did the reviewing and volume was low enough for that to work.

### Why change now

- **Has the original problem changed?** Yes. Volume reached 292 pull requests per 14 days, and the reviewing is largely done by CI and agent review rather than by a human reading commits in sequence.
- **Is there a better solution now?** The correctness gates already in place made the only correct blocking decision in the sample. The proxy is redundant where it is right and costly where it is wrong.
- **Risks of change?** A genuine sprawl pull request could merge where the ceiling would have caught it. Mitigated by the fact that the ceiling never caught one on its own in the sample: #4846 was held by its security gate. The residual risk is named in Consequences.

## Rationale

### Alternatives considered

| Alternative | Pros | Cons | Why not chosen |
|---|---|---|---|
| Keep the ceilings, add a self-service bypass flag | One line, matches the existing pattern | The pattern has a recorded abuse after approval was withheld (`2026-08-07-pr-4402-scope-bypass.md`) | Extends a mechanism with a known failure |
| Keep the ceilings, widen the human bypass | Uses existing machinery | 20 human touchpoints per two weeks already, scaling with volume | Caps throughput at human attention |
| Replace with net authored file surface | Measures reviewer burden more directly | Passes #4846 at 16 files, flags #4718 at 49; backwards on the sample | Wrong on the only case that matters |
| Replace with a convergence metric | Separates spin from rigor in principle | New machinery, no baseline, both inputs forgeable by the gated actor | Deferred to its own decision with its own evidence |
| Model judges whether a diff is "one idea" | No human needed | The model can assert any classification; self-report with a mechanical costume | No verifiable evidence behind the verdict |
| Retire, replace with nothing blocking (chosen) | Pure subtraction; immediate relief; no new surface | Accepts residual sprawl risk | Chosen |

### Trade-offs

This trades a small, unproven protection against sprawl for the removal of a measured, recurring cost. The protection is unproven in the specific sense that in a five-pull-request sample it never made a correct blocking call that a correctness gate did not already make. The cost is measured: 36% of pull requests labeled, 20 human interventions in two weeks, and at least one pull request in the current window spending its output on gate arithmetic.

## Consequences

### Positive

- The 36% `needs-split` rate stops taxing rigorous work.
- The human bypass step disappears, removing 20 touchpoints per two weeks and the throughput cap they impose.
- A wide mechanical change stops requiring dozens of artificial commits.
- One self-attested bypass flag with a recorded abuse history leaves the repository.

### Negative

- A genuine sprawl pull request now depends entirely on correctness gates and review to stop it. If those miss, nothing size-based catches it.
- Losing the label also loses the one event that routinely put a very large pull request in front of a human. Whether that look ever caught anything is not established: a search across the repository for `commit-limit-bypass` finds the label described only as relief a maintainer grants on request, for example `.agents/governance/GOTCHAS.md:238`, and no record of it producing a finding. The lost function is asserted, not measured, and should not be weighted as though it were.
- **The evidence base is thin in the one cell that matters, and this decision holds itself to a weaker standard than ADR-099 applies to its own sample.** Four of the five sampled pull requests are allow-cases, which carry no information about blocking value. The claim that the ceilings never made a correct blocking call therefore rests on #4846 alone, an n of 1. The sample is also subject to survivorship: pull requests the ceiling deterred, or that were split before opening, never appear in it. The five are 4.8% of the 104 labeled.
- No independent wider-sample check was run. An attempt to enumerate the other labeled pull requests in the window was blocked by tooling that cannot list pull requests by label, so the absence of a counterexample is an untested claim rather than a negative result.

### Neutral

- The advisory output stays, so the information a reviewer used is still printed. Only the blocking authority is removed.
- `.claude/rules/universal.md` keeps one idea per commit as a convention. Conventions and mechanical preconditions are different things, and only the second is retired.

## Impact on Dependent Components

| Component | Dependency | Required update | Risk |
|---|---|---|---|
| `scripts/validation/pr_commit_count.py` | Direct | Return 0 in all cases; keep reporting | Low |
| `scripts/validation/git_hook_policy.py` | Direct | `check_atomic_commit` advisory | Medium |
| `scripts/detect_scope_explosion.py` | Direct | Demote `BLOCK_THRESHOLD` (line 50) to advisory FIRST; then add process-record exclusions; then remove `SKIP_SCOPE_CHECK` at line 492. Removing the flag without the demotion ships a blocking gate with no relief | Medium |
| `lefthook.yml` | Direct | Jobs stay, exit codes become 0 | Low |
| `CONTRIBUTING.md` | Direct | Remove the bypass-label procedure | Low |
| `.agents/governance/PROJECT-CONSTRAINTS.md:125` | Direct | Record the constraint as retired, with this ADR as the reason | Medium |
| `.claude/rules/governance.md` MUST-1 and MUST NOT 1 | Direct | This decision edits a file under `.agents/governance/`, so MUST-1 requires human approval, and it reduces a review requirement, so MUST NOT 1 requires a unanimous-consensus ADR. Both apply to this ADR and to its implementation pull request | High |
| `.claude/rules/universal.md` MUST-6 | Direct | Restate as convention, not mechanical precondition | Medium |
| QA and session evidence rebind | Direct | Fix the every-merge refire | Medium |

## Implementation Notes

One phase. No dependency on repository configuration, no new gate, no new required check. Each item is independently revertible by restoring a return value.

Order: fix the rebind generator; demote `pr_commit_count.py`; demote `check_atomic_commit` early, so that this change's own wide diff is not sliced by the cap it retires; demote the scope `BLOCK_THRESHOLD` and add the process-record exclusions; then remove `SKIP_SCOPE_CHECK`; then update the documents. The last two are ordered, not interchangeable, per Decision items 3 and 4.

### Time-box and re-measure

Because the blocking-value claim rests on a single pull request, this retirement is provisional rather than permanent. Ninety days after the implementation lands, re-measure against a stated selection method over the labeled population: whether any pull request merged in the interval should not have, and whether any correctness gate failure was reached later than it would have been under the ceilings. If either shows harm, the ceilings return, informed by what the interval revealed. If neither does, the retirement stands and the follow-up closes.

This is the standard ADR-099 applies to its own ADR sample, and it is applied here for the same reason: a decision resting on an undisclosed or very small sample earns a re-measurement, not an exemption.

### Follow-up, not part of this decision

- Commit thrash as a token-budget control, if it proves needed, with its own evidence.
- Whether the retired ceilings should be re-measured against a larger stratified sample of the 104 labeled pull requests, to confirm the five-pull-request result holds.

## Related Decisions

- ADR-086, lefthook local hook orchestration
- ADR-099, enforcement planes. Not a disjoint scope: ADR-099's plane rule classifies the gates this decision retires as P0, and therefore advisory, which is the same conclusion reached here from cost evidence rather than from the invariant. This decision also removes `SKIP_SCOPE_CHECK`, one of the four root-cause exhibits ADR-099 cites. Neither decision depends on the other landing

## References

- `.agents/governance/PROJECT-CONSTRAINTS.md:125`, the ceiling rationale and its single-incident basis
- `.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md`, self-attested approval after refusal
- `.agents/retrospective/2026-08-17-governance-bureaucracy-critical-review.md`, the 94% self-inflicted issue measurement and the #5103 rebind finding
- `scripts/detect_scope_explosion.py:492`, the unverified bypass flag
- Pull requests #4846, #4718, #5036, #5152, #5103, #5107, the sample
