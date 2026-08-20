# Debate Log: ADR-098 and ADR-099

Four rounds, six roles (architect, critic, independent-thinker, security, analyst, high-level-advisor). Convened 2026-08-20 on a proposal that began as one ADR and split into two.

Final tally: **6 Accept, 0 Block.**

## What was proposed, and what it became

The question that started it: are the pull request size gates earning their cost, given that in-flight pull requests work around them and the gates may be artifacts of a less capable era.

The first draft was a three-tier autonomy model organized around who approves what. The panel rejected it 4 Block to 2 Disagree-and-Commit, and the rejection reshaped the work twice:

1. **Round 1 killed the tier framing.** Tier 3 was scoped to governance prose. Three reviewers independently found the same defect: protecting prose while the enforcement code sits in the autonomous tier inverts the problem, because an actor can comply with prose textually while rewriting the enforcer beneath it. High-level-advisor supplied the evidence the draft had missed, issue #5099.
2. **Round 2 killed the replacement metric.** The redesign proposed replacing commit count with a convergence signal. Independent-thinker, high-level-advisor, and analyst converged from different directions on dropping it: it changed no outcome on the sample, it was new machinery with no baseline in a repository where 94% of open issues are its own automation breaking itself, and both its inputs are forgeable by the actor it would gate.

The result is a split. ADR-098 is pure subtraction and ships alone. ADR-099 carries the invariant and is phased behind control plane hardening.

## Findings that changed the outcome

**The deadlock claim was wrong.** ADR-099's load-bearing mechanism was that required status checks configured by name make gate deletion a deadlock rather than a bypass. Critic, architect, and security each attacked it and found two holes: a job skipped by a job-level `if:` reports a `skipped` conclusion that GitHub treats as satisfying the requirement, and a job that keeps its name while replacing its body passes, because a same-repository `pull_request` event runs the head's workflow definition. This repository already ships the first shape in `.github/workflows/passive-context-budget.yml`. The fix was to state the mechanism precisely (deadlock on non-trigger, pass on job-level skip) and require verification jobs to run the base-ref definition.

**The control plane was assumed, then found unverifiable, then found reachable.** The first draft claimed the ruleset state was unknown because `gh api` returned 403. Architect corrected that: the baseline is in-tree at `scripts/validation/ruleset_params_baseline.json` and `scripts/ci/ruleset_required_contexts.py`. Reading it produced worse news than not knowing, `required_approving_review_count` is `0`, so CODEOWNERS gates nothing, and CODEOWNERS covers five review-prompt globs, not itself and not any enforcement path.

Security then found the finding that falsified the design's premise outright. `BOT_PAT` requires classic `repo` scope by the workflow's own error text, is spent on `gh pr review --approve`, is referenced by seven workflows, and the repository has exactly one environment-gated job. Secrets reach same-repository `pull_request` runs, and the loop authors same-repository branches. So a pull request can read the token and edit the ruleset directly, and can mint the approval that would satisfy any review count the decision installs. The plane table's claim that the control plane is writable "only by a credential the loop does not hold" was false of this repository. ADR-099 now says so in its own text and makes token containment the first hardening item.

**A subtraction ADR was about to ship a tightening.** Independent-thinker and critic separately found that ADR-098 described the scope check as advisory when `scripts/detect_scope_explosion.py:50` sets `BLOCK_THRESHOLD = 50` and the script returns 1 above it. Removing `SKIP_SCOPE_CHECK` on that basis would have left a blocking gate with no relief at all. The fix demotes the threshold and orders it explicitly before the flag removal.

**Two governance rules the drafts shipped against.** Independent-thinker found `.claude/rules/governance.md` MUST-1 (human approval, auto-merge prohibited for governance files) unlisted in the impact table. Critic and high-level-advisor found MUST NOT 1 (no reducing review requirements without a unanimous-consensus ADR) uncited. Both decisions reduce review requirements, so both rules bind both ADRs and their implementation pull requests.

## Evidence corrections made during the debate

Two claims were withdrawn after checking, which is recorded because the corrections matter as much as the findings.

- Critic's round-1 claim that ADR-021 mandates cross-vendor review panels was overstated and withdrawn in round 3. `AI-REVIEW-MODEL-POLICY.md` mandates explicit per-job model routing and forbids PASS under insufficient evidence. It does not require cross-vendor panels. Nothing binds subagent panel composition.
- The orchestrator's claim that Phase 0 was blocked by a 403 was wrong, corrected by architect in round 3.

The panel is single-vendor: all six roles pin Anthropic models. That is recorded in ADR-099 as accepted residual risk rather than solved, and it is the sharpest limitation on how much this debate's own agreement should be weighted.

## Unresolved and deliberately deferred

- **The debate mandate's catch rate is unmeasured.** Independent-thinker's condition, that the oversight mechanism be measured rather than assumed, is filed as a follow-up blocking completion of ADR-099 Phase 2 rather than its start. Independent-thinker flagged in round 4 that this permits opening Phase 2 with the deciding number still unmeasured. Accepted, because Phases 0 and 1 alone are a stated acceptable terminal state.
- **ADR-098's blocking-value evidence is an n of 1.** Four of five sampled pull requests are allow-cases. The claim that the ceilings never made a correct blocking call rests on #4846 alone, and is subject to survivorship, since deterred and pre-split pull requests never appear. Analyst could not enumerate the wider labeled population due to a tooling gap, so no independent counterexample search was run. Mitigated by a 90 day re-measure trigger rather than resolved.
- **Tag protection** and the `BOT_PAT` scope question (whether reducing below classic `repo` conflicts with minting real-user reviews) are Phase 0 inventory work.

## Round 5: the base moved under the conclusions

Not a debate round. Recorded here because it changed cited facts after the panel had finished, and because the mechanism generalizes.

Minutes after the pull request opened, the owner merged `main` into the branch. That merge carried PR #5179, "remove session, session-init, session-end, session-log-fixer skills and session protocol," which deleted `.agents/SESSION-PROTOCOL.md`.

ADR-099 cited that file as a live six-agent debate trigger, in the PR #5177 incident and in the description of what the mandate covers. The same merge moved `check_adr_review_policy` from line 1390 to 1382, moved the `skip: merge` entry from lines 199-200 to 198-199, and shifted governance MUST-1 from line 12 to 13. Every one of those was verified true when written and false forty minutes later.

Every citation in both documents was re-run against the merged tree. Six held unchanged. Five were corrected. One finding was substantive rather than cosmetic: the trigger set has already narrowed to ADR files alone, which is a partial move toward what ADR-099's Application A proposes, so the ADR now says that instead of proposing it as though nothing had happened. The PR #5177 evidence survives the deletion, because what failed there was that a session could decline the mandated review and still commit, and removing one path from the trigger set does not touch that.

Nothing in the repository catches this class of drift. `.agents/**` is excluded from markdownlint, and `orphan-ref-validator` matches file paths and skill names rather than line numbers or prose claims about another file's contents. `.claude/rules/canonical-source-mirror.md` names the failure mode under "True when you wrote it is not true at merge" and states the remedy plainly: the only check is the one the author runs, against the tree that will actually merge.

Two review bots also engaged in this window. Cursor Bugbot flagged the `changesCommitted` evidence for naming more commits than `endingCommit` records, which was correct: the prose said two commits when the branch had grown past that, and it did not explain why the commit that records the SHA is necessarily not the commit it names. Its autofix agent pushed a terser replacement; this branch keeps a fuller one that preserves the session-log MUST-2 rationale, since that rationale is what made the original wording confusing.

## Verdicts

| Round | architect | critic | independent-thinker | security | analyst | high-level-advisor |
|---|---|---|---|---|---|---|
| 1, tier sketch | Block | Block | D&C | Block | Block | D&C |
| 2, single ADR | Block | Block | D&C | Block | Block | D&C |
| 3, split pair | D&C | Block on 098, D&C on 099 | D&C | Block | D&C | Accept |
| 4, revised | Accept | Accept both | Accept | Accept | not re-run, conditions met verbatim | not re-run, condition met |
