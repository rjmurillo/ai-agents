# Debate Log: ADR-098 and ADR-099

Six rounds, six roles (architect, critic, independent-thinker, security, analyst, high-level-advisor). Convened 2026-08-20 on a proposal that began as one ADR and split into two.

**Council decision, round 6, all six roles run on the final text: 3 Accept, 3 Disagree-and-Commit, 0 Block. Consensus reached** under this repository's contract, which requires every role to return Accept or Disagree-and-Commit.

The decision is a review verdict, not an acceptance. Both ADRs remain `status: proposed` and require human approval under `.claude/rules/governance.md` MUST-1, plus a unanimous-consensus record under MUST NOT 1, before either can be accepted.

Round 4 was reported as "6 Accept, 0 Block" in an earlier revision of this log. That was wrong: only four roles were re-run and two positions were inferred. A bot reviewer caught it, and round 5 exists because of that catch.

## What was proposed, and what it became

The question that started it: are the pull request size gates earning their cost, given that in-flight pull requests work around them and the gates may be artifacts of a less capable era.

The first draft was a three-tier autonomy model organized around who approves what. The panel rejected it 4 Block to 2 Disagree-and-Commit, and the rejection reshaped the work twice:

1. **Round 1 killed the tier framing.** Tier 3 was scoped to governance prose. Three reviewers independently found the same defect: protecting prose while the enforcement code sits in the autonomous tier inverts the problem, because an actor can comply with prose textually while rewriting the enforcer beneath it. High-level-advisor supplied the evidence the draft had missed, issue #5099.
2. **Round 2 killed the replacement metric.** The redesign proposed replacing commit count with a convergence signal. Independent-thinker, high-level-advisor, and analyst converged from different directions on dropping it: it changed no outcome on the sample, it was new machinery with no baseline in a repository where 94% of open issues are its own automation breaking itself, and both its inputs are forgeable by the actor it would gate.

The result is a split. ADR-098 is pure subtraction and ships alone. ADR-099 carries the invariant and is phased behind control plane hardening.

## Findings that changed the outcome

**The deadlock claim was wrong.** ADR-099's load-bearing mechanism was that required status checks configured by name make gate deletion a deadlock rather than a bypass. Critic, architect, and security each attacked it and found two holes: a job skipped by a job-level `if:` reports a `skipped` conclusion that GitHub treats as satisfying the requirement, and a job that keeps its name while replacing its body passes, because a same-repository `pull_request` event runs the head's workflow definition. This repository already ships the first shape in `.github/workflows/passive-context-budget.yml`. The fix was to state the mechanism precisely (deadlock on non-trigger, pass on job-level skip) and require verification jobs to run the base-ref definition.

**The control plane was assumed, then found unverifiable, then found reachable.** The first draft claimed the ruleset state was unknown because `gh api` returned 403. Architect corrected that: the baseline is in-tree at `scripts/validation/ruleset_params_baseline.json` and `scripts/ci/ruleset_required_contexts.py`. Reading it produced worse news than not knowing, `required_approving_review_count` is `0`, so CODEOWNERS gates nothing, and CODEOWNERS covers five review-prompt globs, not itself and not any enforcement path.

Security then found the finding that falsified the design's premise outright. `BOT_PAT` requires classic `repo` scope by the workflow's own error text, is spent on `gh pr review --approve`, is referenced by seven workflows, and the repository has exactly one environment-gated job. Secrets reach same-repository `pull_request` runs, and the loop authors same-repository branches. So a pull request can read the token and act with that account's authority. External review later narrowed this: the repository's two collaborators are `rjmurillo` (admin) and `rjmurillo-bot` (write), ruleset mutation requires admin, and classic `repo` scope does not raise an account's role. The verified impact is token theft plus **minting pull request approvals**, which defeats the review count Phase 0 installs; direct ruleset mutation is not established. ADR-099 now states the narrower claim and makes determining the token's owning account a Phase 0 item.

**A subtraction ADR was about to ship a tightening.** Independent-thinker and critic separately found that ADR-098 described the scope check as advisory when `scripts/detect_scope_explosion.py:50` sets `BLOCK_THRESHOLD = 50` and the script returns 1 above it. Removing `SKIP_SCOPE_CHECK` on that basis would have left a blocking gate with no relief at all. The fix demotes the threshold and orders it explicitly before the flag removal.

**Two governance rules the drafts shipped against.** Independent-thinker found `.claude/rules/governance.md` MUST-1 (human approval, auto-merge prohibited for governance files) unlisted in the impact table. Critic and high-level-advisor found MUST NOT 1 (no reducing review requirements without a unanimous-consensus ADR) uncited. Both decisions reduce review requirements, so both rules bind both ADRs and their implementation pull requests.

## Evidence corrections made during the debate

Two claims were withdrawn after checking, which is recorded because the corrections matter as much as the findings.

- Critic's round-1 claim that ADR-021 mandates cross-vendor review panels was overstated and withdrawn in round 3. `AI-REVIEW-MODEL-POLICY.md` mandates explicit per-job model routing and forbids PASS under insufficient evidence. It does not require cross-vendor panels. Nothing binds subagent panel composition.
- The orchestrator's claim that Phase 0 was blocked by a 403 was wrong, corrected by architect in round 3.

The panel is single-vendor: all six roles pin Anthropic models. That is recorded in ADR-099 as accepted residual risk rather than solved, and it is the sharpest limitation on how much this debate's own agreement should be weighted.

## Unresolved and deliberately deferred

- **The debate mandate's catch rate is unmeasured.** Independent-thinker's condition, that the oversight mechanism be measured rather than assumed, is filed as a follow-up blocking completion of ADR-099 Phase 2 rather than its start. Independent-thinker flagged in round 4 that this permits opening Phase 2 with the deciding number still unmeasured. Accepted, because Phases 0 and 1 alone are a stated acceptable terminal state.
- **ADR-098's blocking-value evidence was an n of 1 until the population was enumerated.** A bot reviewer supplied the query the panel believed did not exist. Seven closed-unmerged `needs-split` pull requests exist in the window; exactly one carries `commit-limit-bypass`, and it was independently failing its own security gate. Five of seven were characterized, none stopped by the ceiling. Survivorship remains: pull requests the ceiling deterred appear in no query.
- **Tag protection** and the `BOT_PAT` scope question (whether reducing below classic `repo` conflicts with minting real-user reviews) are Phase 0 inventory work.

## Between rounds: the base moved under the conclusions

Not a debate round. Recorded here because it changed cited facts after the panel had finished, and because the mechanism generalizes.

Minutes after the pull request opened, the owner merged `main` into the branch. That merge carried PR #5179, "remove session, session-init, session-end, session-log-fixer skills and session protocol," which deleted `.agents/SESSION-PROTOCOL.md`.

ADR-099 cited that file as a live six-agent debate trigger, in the PR #5177 incident and in the description of what the mandate covers. The same merge moved `check_adr_review_policy` from line 1390 to 1382, moved the `skip: merge` entry from lines 199-200 to 198-199, and shifted governance MUST-1 from line 12 to 13. Every one of those was verified true when written and false forty minutes later.

Every citation in both documents was re-run against the merged tree. Six held unchanged. Five were corrected. One finding was substantive rather than cosmetic: the trigger set has already narrowed to ADR files alone, which is a partial move toward what ADR-099's Application A proposes, so the ADR now says that instead of proposing it as though nothing had happened. The PR #5177 evidence survives the deletion, because what failed there was that a session could decline the mandated review and still commit, and removing one path from the trigger set does not touch that.

Nothing in the repository catches this class of drift. `.agents/**` is excluded from markdownlint, and `orphan-ref-validator` matches file paths and skill names rather than line numbers or prose claims about another file's contents. `.claude/rules/canonical-source-mirror.md` names the failure mode under "True when you wrote it is not true at merge" and states the remedy plainly: the only check is the one the author runs, against the tree that will actually merge.

Two review bots also engaged in this window. Cursor Bugbot flagged the `changesCommitted` evidence for naming more commits than `endingCommit` records, which was correct: the prose said two commits when the branch had grown past that, and it did not explain why the commit that records the SHA is necessarily not the commit it names. Its autofix agent pushed a terser replacement; this branch keeps a fuller one that preserves the session-log MUST-2 rationale, since that rationale is what made the original wording confusing.


## Round 5: the panel re-run on corrected text

Called because external bot review of the live pull request falsified four claims the panel had accepted, and because the round-4 tally was found to be unsupported.

| Role | Verdict | Condition, and disposition |
|---|---|---|
| security (2.0x) | Accept | Blocked first on context spoofing and on containment scoped to PATs only. Both applied, then confirmed in text. |
| architect | Accept | Required the substitution case named and `require_code_owner_review` added. Applied. |
| high-level-advisor | Accept | Required the go/no-go default flipped to abandon Phases 2 and 3 absent a measured catch rate. Applied. |
| independent-thinker | Accept | Three prose fixes, including that the error-disclosure clause "converts an error into a credential." Applied. |
| analyst | Disagree-and-Commit | Verified the #5099 correction and every citation independently. Withheld a clean Accept for counts it had not itself verified; those were then verified. |
| critic | Disagree-and-Commit | Five defects, all applied: the spoofing denial missed `checks: write`; the gate names four residuals, not two; the bypass-label inference was invalid; a cited convention does not exist; fail-closed contradicted itself. |

### What round 5 changed

Critic's findings were the sharpest of the debate and each was verified before it was applied:

- **The spoofing fix was half a fix.** A required context is satisfiable by a check run as well as a commit status. `.github/workflows/claude.yml` triggers on `pull_request` and grants `checks: write` and `statuses: write` together; three workflows grant the former. Denying only `statuses: write` left the anchor spoofable.
- **The residual count was wrong.** `run_completion_gate.py` names four residuals in its own trust model: dynamic imports, untracked files, the dispatcher itself, and a CWE-367 verify-then-dispatch window. The decision claimed two. Only one of the four is addressed by moving planes, and the ADR now says which.
- **The enumeration's inference was invalid.** `commit-limit-bypass` marks relief granted, not the blocking threshold being reached. #4821 has 29 commits and no label, which is exactly the counterexample class the enumeration was meant to rule out. Two of seven remain unread and the label cannot clear them, so ADR-098 now says the population check is incomplete rather than closed.
- **A cited convention does not exist.** Both ADRs claimed one-idea-per-commit is documented in `.claude/rules/universal.md`. A search returns nothing; MUST-6 is the five-file rule being retired. Nothing survives the retirement, and the text now says so.

### The observation worth keeping

Every round-5 correction originated in bot review of the live pull request, not in the agent panel. The panel had converged to Accept twice on text containing a closed issue described as a live CVSS 8.8, a spoofable anchor, an invalid inference, and a citation to a rule that does not exist.

All six panel roles pin Anthropic models. This is what the single-vendor limitation recorded in ADR-099 predicts, observed rather than theorized, and it is the strongest evidence in this log for why cross-vendor review belongs in the design rather than in a follow-up. It is also the reason the panel's own agreement should be weighted below the external findings it missed.


## Round 6: the council decision

Called because round 5's votes were rendered on text that eight subsequent corrections had changed. Carrying them forward would have repeated the inference error a bot reviewer caught after round 4.

| Role | Verdict | Reservation carried |
|---|---|---|
| architect | Accept | Publisher identity had no phase owner; two editorial fixes. Applied. |
| analyst | Accept | Re-verified the corrected gate contract line by line against `pr_commit_count.py` and every countable figure in the tree. All matched. Asked that #4814 and #4733 be read before implementation. Done, below. |
| high-level-advisor | Accept | Freeze and hand to the owner; read the two unread pull requests first. Done. |
| critic | Disagree-and-Commit | The 36% measures an advisory notice, not a block; the enumeration shows zero blocks rather than one; approval-minting does not satisfy `require_code_owner_review`. All applied. |
| security (2.0x) | Disagree-and-Commit | The permission denial is not implementable at P2 and must be stated as an advisory lint; the anchor must be an App-published check run with `integration_id` pinned, because a commit status is postable by any `repo`-scope token; baseline the environment deployment policy. All applied. |
| independent-thinker | Disagree-and-Commit | A double standard on selection method between the two ADRs, and a competing explanation for the panel's blind spot. Recorded below. |

### The enumeration completed

Two pull requests were unread when round 5 closed. Both were read for this round. #4814 carries 13 commits, #4733 carries 11, neither carries the bypass label, and both sit under the effective ceiling. Neither is a counterexample.

That completes the closed-unmerged population at seven of seven and changes the finding's shape: because #4846 carried `commit-limit-bypass`, meaning relief was granted, the enumerated population contains no pull request the blocking ceiling actually stopped. The gate's harm-prevention record over this window is empty rather than thin.

### Two explanations for the panel's blind spot, one of them cheaper

The panel converged to Accept twice on text carrying eight load-bearing factual errors, every one of which was found outside the panel. The obvious reading is the single-vendor correlation this log already records, since all six roles pin Anthropic models.

Independent-thinker supplied a competing explanation that is cheaper and, importantly, falsifiable: **no panel role was ever assigned to verify claims against the tree.** The wrong threshold contract sat in plain text at `scripts/validation/pr_commit_count.py:62-71`; reading it costs one command, and a reviewer of any vendor reasoning over prose alone would have missed it identically.

The two hypotheses predict different fixes, so the difference matters. The test: replay the eight errors against a same-vendor role whose only mandate is to open every cited file. If it catches most of them, the vendor framing is over-weighted and the real defect is role design.

Both are recorded here because closing on the vendor explanation would foreclose a question the cheaper fix answers, and because the falsification harness ADR-099 already defers is the instrument that would settle it. Analyst's round-6 pass is weak evidence for the second hypothesis: given an explicit mandate to re-verify numbers against the tree, it checked every countable figure and found them all correct.

### Where the review ends

High-level-advisor's read, which the orchestrator accepts: freeze the text. Six rounds on six files, with the external reviewers out-yielding the panel, means another round buys marginal prose and spends credibility the panel needs. What remains is not more review; it is the owner's decision under MUST-1 and MUST NOT 1.

## Verdicts

| Round | architect | critic | independent-thinker | security | analyst | high-level-advisor |
|---|---|---|---|---|---|---|
| 1, tier sketch | Block | Block | D&C | Block | Block | D&C |
| 2, single ADR | Block | Block | D&C | Block | Block | D&C |
| 3, split pair | D&C | Block on 098, D&C on 099 | D&C | Block | D&C | Accept |
| 4, revised | Accept | Accept both | Accept | Accept | not re-run | not re-run |
| 5, corrected | Accept | D&C | Accept | Accept | D&C | Accept |
| 6, final | Accept | D&C | D&C | D&C | Accept | Accept |
