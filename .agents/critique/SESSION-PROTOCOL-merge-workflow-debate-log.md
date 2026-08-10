# SESSION-PROTOCOL Merge Workflow Debate

## Decision under review

Document strict branch freshness plus GitHub squash auto-merge as the
repository's default pull request landing workflow. Record the failed Trunk
Merge Queue trial without claiming every queue implementation will fail.

## Evidence

| Claim | Evidence |
|-------|----------|
| Strict freshness enabled | Ruleset 11104075 API returned `strict: true` |
| No merge queue rule | Ruleset 11104075 API returned zero `merge_queue` rules |
| Auto-merge mechanism works | PR #4819 merged at `3b3c53e2f` |
| Trunk trial did not merge | PR #4814 closed without merge; issue #4815 |
| Trunk incident cost | 18 draft PRs and 695 workflow runs in the measured window |
| Timeout basis | PR #4819 slowest required check: 1094 seconds |

## Round 1

| Reviewer | Vote | Blocking concern |
|----------|------|------------------|
| Architect | ACCEPT | None |
| Critic | BLOCK | Auto-merge enablement could be mistaken for completion; unattended critic cross-reference missing |
| Independent thinker | DISAGREE_AND_COMMIT | N=1 overclaimed; queue prohibition too broad; local prompt gate lacked evidence |
| Security | Not counted | Reviewed unrelated files, so the result was discarded |
| Analyst | ACCEPT | Metrics needed a durable citation; merge command should be explicit |
| High-level advisor | BLOCK | Could not access the diff, so refused to fabricate a vote |

## Round 1 changes

1. Made `MERGED` the terminal condition. Auto-merge enablement is not task
   completion.
2. Added a 30-minute escalation rule using exact
   `gh pr checks --required` blockers and user-accepted handoff.
3. Cross-referenced the unattended critic requirement.
4. Added explicit `git fetch origin main` and
   `git merge --no-edit origin/main` commands.
5. Required QA evidence for every locally-run quality axis.
6. Reframed PR #4819 as initial mechanism proof, not throughput proof.
7. Allowed future queue trials only by user decision with cost ceiling,
   success target, time limit, and rollback.
8. Cited issue #4815 and PR #4814, and described the Trunk result as a
   configuration incompatibility rather than a category judgment.

## Round 2

| Reviewer | Vote | Remaining P0/P1 |
|----------|------|-----------------|
| Architect | ACCEPT | None |
| Critic | ACCEPT | None |
| Independent thinker | ACCEPT | None |
| Security | ACCEPT | None |
| Analyst | ACCEPT | None |
| High-level advisor | ACCEPT | None |

The critic and advisor noted P2 duplication between the protocol and GOTCHAS.
GOTCHAS now cross-references Phase 2.8 and retains only the incident trap and
symptom. The advisor also asked for the 30-minute basis. PR #4819's slowest
required check completed in 1094 seconds, leaving 706 seconds before
escalation; the protocol records that measurement and requires remeasurement
when required checks change.

## Strategic lenses

| Lens | Result |
|------|--------|
| Chesterton's Fence | PASS. The failed trial and rollback are preserved with evidence. |
| Reversibility | PASS. Future bounded queue experiments remain possible by user decision. |
| Core vs context | PASS with caution. Merge policy is context, but the incident cost justifies a compact guardrail. |
| Second-system effect | PASS. No custom orchestrator or new merge service is introduced. |

## Consensus

Six of six reviewers ACCEPT. No P0 or P1 issues remain.
