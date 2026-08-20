# Debate Log: ADR-100 and ADR-101

Six rounds, six roles (architect, critic, independent-thinker, security, analyst, high-level-advisor). Convened 2026-08-20 on a proposal that began as one ADR and split into two.

**Council decision, round 6, all six roles run on the round-6 text: 3 Accept, 3 Disagree-and-Commit, 0 Block. Consensus reached** under this repository's contract, which requires every role to return Accept or Disagree-and-Commit.

**That consensus does not cover the current text, and this log previously said "final text," which was wrong.** External bot review continued after round 6 and forced material changes to both decisions: the open population was enumerated and then re-measured from head refs, the publisher pin was scoped and promoted to a prerequisite, the CODEOWNERS identity deadlock was added, both commit-ceiling enforcement sites were named, the bypass figure was reduced to what the query supports, the 90 day counterfactual was narrowed to the CI contract, and the approval producer gained three placement requirements. None of that was re-run through the panel. The contract requires consensus on the revision being accepted, so the accurate statement is that six roles reached consensus on the round-6 text and the text has moved substantially since under a different review mechanism. Whoever accepts these ADRs should either re-run the panel on the current revision or record that they are accepting on the strength of the external review instead.

The decision is a review verdict, not an acceptance. Both ADRs remain `status: proposed`. Note the scope, corrected during review: `.claude/rules/governance.md` is scoped to `.agents/governance/**`, so MUST-1 and MUST NOT 1 bind the implementation pull requests that edit governance files, not these architecture proposals.

Round 4 was reported as "6 Accept, 0 Block" in an earlier revision of this log. That was wrong: only four roles were re-run and two positions were inferred. A bot reviewer caught it, and round 5 exists because of that catch.

## What was proposed, and what it became

The question that started it: are the pull request size gates earning their cost, given that in-flight pull requests work around them and the gates may be artifacts of a less capable era.

The first draft was a three-tier autonomy model organized around who approves what. The panel rejected it 4 Block to 2 Disagree-and-Commit, and the rejection reshaped the work twice:

1. **Round 1 killed the tier framing.** Tier 3 was scoped to governance prose. Three reviewers independently found the same defect: protecting prose while the enforcement code sits in the autonomous tier inverts the problem, because an actor can comply with prose textually while rewriting the enforcer beneath it. High-level-advisor supplied the evidence the draft had missed, issue #5099.
2. **Round 2 killed the replacement metric.** The redesign proposed replacing commit count with a convergence signal. Independent-thinker, high-level-advisor, and analyst converged from different directions on dropping it: it changed no outcome on the sample, it was new machinery with no baseline in a repository where 94% of open issues are its own automation breaking itself, and both its inputs are forgeable by the actor it would gate.

The result is a split. ADR-100 is pure subtraction and ships alone. ADR-101 carries the invariant and is phased behind control plane hardening.

## Findings that changed the outcome

**The deadlock claim was wrong.** ADR-101's load-bearing mechanism was that required status checks configured by name make gate deletion a deadlock rather than a bypass. Critic, architect, and security each attacked it and found two holes: a job skipped by a job-level `if:` reports a `skipped` conclusion that GitHub treats as satisfying the requirement, and a job that keeps its name while replacing its body passes, because a same-repository `pull_request` event runs the head's workflow definition. This repository already ships the first shape in `.github/workflows/passive-context-budget.yml`. The fix was to state the mechanism precisely (deadlock on non-trigger, pass on job-level skip) and require verification jobs to run the base-ref definition.

**The control plane was assumed, then found unverifiable, then found reachable.** The first draft claimed the ruleset state was unknown because `gh api` returned 403. Architect corrected that: the baseline is in-tree at `scripts/validation/ruleset_params_baseline.json` and `scripts/ci/ruleset_required_contexts.py`. Reading it produced worse news than not knowing, `required_approving_review_count` is `0`, so CODEOWNERS gates nothing, and CODEOWNERS covers five review-prompt globs, not itself and not any enforcement path.

Security then found the finding that falsified the design's premise outright. `BOT_PAT` requires classic `repo` scope by the workflow's own error text, is spent on `gh pr review --approve`, is referenced by seven workflows, and the repository has exactly one environment-gated job. Secrets reach same-repository `pull_request` runs, and the loop authors same-repository branches. So a pull request can read the token and act with that account's authority. External review later narrowed this: the repository's two collaborators are `rjmurillo` (admin) and `rjmurillo-bot` (write), ruleset mutation requires admin, and classic `repo` scope does not raise an account's role. The verified impact is token theft plus **minting pull request approvals**, which defeats the review count Phase 0 installs; direct ruleset mutation is not established. ADR-101 now states the narrower claim and makes determining the token's owning account a Phase 0 item.

**A subtraction ADR was about to ship a tightening.** Independent-thinker and critic separately found that ADR-100 described the scope check as advisory when `scripts/detect_scope_explosion.py:50` sets `BLOCK_THRESHOLD = 50` and the script returns 1 above it. Removing `SKIP_SCOPE_CHECK` on that basis would have left a blocking gate with no relief at all. The fix demotes the threshold and orders it explicitly before the flag removal.

**Two governance rules the drafts shipped against.** Independent-thinker found `.claude/rules/governance.md` MUST-1 (human approval, auto-merge prohibited for governance files) unlisted in the impact table. Critic and high-level-advisor found MUST NOT 1 (no reducing review requirements without a unanimous-consensus ADR) uncited. Both decisions reduce review requirements, so both rules apply. What they bind was itself corrected later in the review and is stated at the top of this log: `.claude/rules/governance.md` is scoped by its frontmatter to `.agents/governance/**`, so MUST-1 and MUST NOT 1 gate the implementation pull requests, which edit governance files, and not these two architecture proposals. The finding stands; the scope claim in the first version of this paragraph did not.

## Round 7: the panel re-run, with verification assigned

Round 7 exists because a reviewer applied the contract correctly: consensus was recorded on the round-6 text, both decisions changed materially afterwards under bot review, and the contract requires consensus on the revision being accepted. The panel was re-run against head `a6bfda1b6`.

**One thing was changed about how it was run, and it was changed as an experiment.** This log records two competing explanations for why six rounds of this panel converged to Accept on text holding a dozen-plus factual errors: single-vendor correlation across six Anthropic-model roles, and the cheaper, falsifiable alternative that no role was ever assigned to verify claims against the tree. Round 7 assigns verification to every role explicitly, and makes it the analyst's whole job. If the panel comes back clean, the correlation explanation gains support. If it finds real defects, the assignment was the missing part.

**It found real defects, in text that had already survived ten external review rounds.** That is evidence for the cheaper explanation, and it means the fix is a role assignment rather than a vendor change. Recorded before the verdicts, because the result is more useful than the votes.

| Role | Verdict | Load-bearing finding |
|---|---|---|
| high-level-advisor | Disagree-and-Commit | ADR-100 item 1 said `pr_commit_count.py` "returns 0 in every case". It returns 2 and 3 on its error paths (`:461`, `:480`, `:483`). Also: cut the 90 day re-measure, split the two decisions, freeze the text |
| security | Disagree-and-Commit | The manufactured-green skip-job pattern is live on a **required** context, not only the harmless one this decision cited. Also `dismiss_stale_reviews_on_push` is unbaselined, and a citation pointed at a comment header |
| analyst | Accept | Zero false claims across every checkable citation, including an independent reconstruction of the three PR commit counts by a different method (GitHub API rather than `git rev-list`), converging on identical numbers |
| architect | Disagree-and-Commit | Requirement 1 forbids job-level `if:` and path filters, and 3 of the 9 required contexts satisfy it while gating every substantive step on a path output, so the rule is satisfiable by moving the condition down one level. Impact table omitted the live violations and repeated a claim the body corrects |
| critic | Disagree-and-Commit | "All three were relieved" survives at two summary lines and is refuted by the document's own #5178 evidence. Decision item 5 named no component while being ordered first. The eight-record corpus is the only count with no query attached |
| independent-thinker | Disagree-and-Commit | ADR-100 rests on correctness gates as the replacement; ADR-101 establishes those gates are P0 artifacts the gated actor can rewrite. And one of the eight records, Session 3468, is the gate working as designed, coded as a cost |

**Round 7 result: 1 Accept, 5 Disagree-and-Commit, 0 Block. Consensus reached** under the contract, which requires every role to return Accept or Disagree-and-Commit.

**The experiment returned a result, and it is the cheaper hypothesis.** Assigning verification produced real defects in text that had already survived eleven external bot rounds: an unreconciled contradiction between two lines of ADR-101, a rule satisfiable by relocating a condition, a decision item that named no component, a withdrawn inference surviving in two summary sentences, and a structural objection nobody had raised. So the panel's prior blindness was a missing role assignment rather than a property of the models, and the fix costs one sentence per role prompt. Recorded as the actionable finding of this round, above the verdicts, because it transfers and the verdicts do not.

The analyst's Accept is the weakest signal in the table and should be read that way: it found nothing false partly because eleven rounds of bot review had already scrubbed the citations it checked. Its value is method independence, not the verdict.

**The required-context finding, and the correction to it.** Security reported that `pytest.yml` pairs `test-result` and `skip-tests` under the same job name `Run Python Tests`, that the name is a pinned required context (`ruleset_required_contexts.py:14`), and that a pull request editing its own path filter therefore yields a green required check with zero tests run. The first two facts check out and are important: this decision had cited only `passive-context-budget.yml`, whose context is not required, and so understated its own thesis in its own repository.

The exploit claim does not survive checking. The filter list at `pytest.yml:69-100` covers `**/*.yml` and also names `.github/workflows/pytest.yml` by path, so any edit to the filter marks Python inputs changed and the real test job runs. The single-pull-request attack closes on itself, deliberately. The residual is a two-pull-request sequence whose first step runs the tests and shows the filter change in its diff. ADR-101 now carries the verified version rather than the reported one.

That correction is worth its own line. A panel role produced a finding, and checking the finding against the tree improved it in both directions: the underlying defect was worse than this decision had recorded, and the attack was less immediate than the reviewer had reported. Verification is not only a filter against false findings; it is what turns a true finding into an accurate one.

**The actor claim came back a third time, in the opening contract.** Two rounds removed "20 human bypass applications" from the cost section and the tables. The Context section's own one-line description of the gate still read "a `commit-limit-bypass` label a human applies", ten lines above the paragraph that withdraws exactly that. Same for the prior-art summary near the end. The lesson is not about this claim: a correction applied by searching for a phrase misses every paraphrase of it, and a decision that states its contract in three places will reintroduce a withdrawn claim in the two that were not searched. Fixed by stating the normative reservation and the enforced permission as separate facts, which is what they are.

**The headline window was 14 days and 18 hours.** `created:2026-08-06..2026-08-20` is date-granular and includes all of August 6, so calling it "the preceding 14 days" against an 18:00Z cutoff overstates precision the query does not have. The counts are unchanged and are now described as date-bounded rather than re-derived at exact timestamp boundaries.

**An ADR number collision that no single-pull-request check can see.** Open pull request #5177 allocates `.agents/architecture/ADR-100-agent-role-metadata-replaces-tier-hierarchy.md` at its current head. This decision allocates `ADR-100-retire-pr-size-ceilings.md`. The filenames differ, so git reports no conflict, both can merge, and `check_adr_uniqueness.py` then fails for whichever lands second. This decision's own QA record reports that check passing, which was true and useless: it runs against one tree, and the conflict lives between two open branches. That is the same shape as everything else recorded here, one plane up. A gate that reads only the artifact under review cannot see a conflict that exists between artifacts.

**The same claim, a third paraphrase, in a third table.** "Returns 0 in every case" was corrected in the decision body, then found again by a panel role in the classifier's impact row, then found again by a bot in the CI-block row. Three instances, three separate corrections, one underlying fact. Combined with the actor claim's three instances, the pattern is now established well enough to state as a rule rather than an anecdote: in a document that restates its subject in prose, a decision item, and two impact tables, correcting the prose reaches one of four. Searching for the phrase reaches the ones that share wording. Nothing reaches a paraphrase except reading every restatement, and no gate in this repository checks a document against itself.

**An impact row that read as authorization.** The `governance.md` MUST-1 row said this decision "replaces that with plane-based enforcement and must retire it explicitly." Phase 3 is what retires MUST-1; Phase 3 requires Phase 2; the go/no-go defaults Phase 2 to abandoned; and retirement independently needs its own unanimous-consensus ADR under MUST NOT 1. So the row granted, in a table, a permission the decision text withholds in three places. Marked conditional. Worth noting which reviewer caught it: a bot reading the table against the phases, not the panel reading the argument.

**A stale count in a field that propagates.** The session objective recorded "four factual errors", a number true when written and wrong by the next round, and `extract_session_episode.py` copies that field verbatim into the episode artifact that feeds memory retrieval. A number that changes every round does not belong in a field that is copied rather than derived. Replaced with number-free wording pointing at this log and the QA report, which are the documents that own the counts.

## Evidence corrections made during the debate

**The cost figure counted labels and said humans, and the repository documents the counterexample in the gate's own source.** ADR-100 asserted "20 human bypass applications" in seven places. The query returns 20 labeled pull requests and says nothing about who labeled them. `scripts/validation/git_hook_policy.py:6055-6070` records an agent applying `commit-limit-bypass` to PR #4735 on 2026-08-08 **because this gate's failure message named the label as the reader's next step** (issue #4782), and states the mechanism directly: "Naming the label as the reader's next step tells whoever tripped the gate to grant themselves a permission they do not hold." The message gained a prohibition; the label gained no enforcement, because a GitHub label carries none.

The correction cuts both ways and both halves are now in the text. The throughput-cost argument weakens: the relief is not reliably a human decision, so it does not reliably cap throughput at human attention. The structural argument strengthens sharply: this is the cleanest instance in the repository of ADR-101's invariant, reached from the opposite direction. The commit ceiling is a P0 and P1 gate whose only relief is a P0-writable artifact that any write-access account can create, with nothing verifying the human maintainer CONTRIBUTING.md requires. The two decisions were written as separate arguments and turn out to describe one defect.

**A counterfactual that cannot be computed.** A later external-review round replaced the 90 day rollback predicate with "replay both retired contracts over each merged pull request." A reviewer showed the local contract is not replayable: it evaluates push ranges rather than branch states, applies two reliefs computed at push time, and a squashed branch has erased the commits it saw. The decision's own PR #5178 case is the proof, with 12 commits in merged history against 33 the pre-push gate actually blocked. Narrowed to the CI contract, with the gap named: the pre-push ceiling has the most first-hand evidence against it and the least ability to be re-measured, and closing that needs push-time telemetry recorded when the ceilings are demoted rather than after.

**Half the debate attestation has no unforgeable source.** Application A requires an attestation carrying the invocation set, the model identifiers, and the diff digest. The base-ref job computes the digest itself, so staleness detection is sound. Nothing in a diff yields which agents ran under which models, and rule 3 forbids trusting a head-produced artifact, so that half is the self-report the application exists to replace with a base-ref signature on it. Only two sources close it: the base-owned job invokes the agents itself, or the provider emits per-invocation signed receipts the base job verifies. Found after the go/no-go had already defaulted Phase 2 to abandoned, and recorded as a second independent reason for that default.

**The session log misstated a blocking requirement as an advisory one, twice.** `serenaActivated` and `serenaInstructions` were recorded at level SHOULD, justified by the absence of symbol-level navigation. AGENTS.md:3 heads the requirement "Serena Init (BLOCKING)" and `.claude/rules/lsp-first.md:83` scopes the advisory clause to navigation, not initialization. Both are now MUST. The requirement was then satisfied rather than argued away, late and recorded as late. Worth keeping in this log because of what the pull request argues: a record that downgrades a gate's level to make itself pass is the failure both ADRs describe, authored by the session describing it.

**Two corrections in a row, in opposite directions, on the same sentence.** The fork consequence in ADR-101 was first written as a flat deadlock, corrected to "forks are unaffected" after a reviewer showed a `workflow_run` job publishes fine against a fork head, then corrected again because that second version contradicted the decision's own fork section. That section had recorded the real state all along: the open question is not whether `workflow_run` can publish, it is whether the **separate publisher App** can attach a check to a fork head commit, which is a runtime-contract question nobody has probed. Both revisions replaced an unproven claim with a different unproven claim. The current text asserts neither and names the probe. Recorded because the failure mode is specific and cheap to repeat: a reviewer refutes half of a claim, and the fix overshoots into asserting the opposite half rather than returning to what the evidence supports.

**A remediation that did not remediate, caught by trigger type.** The Phase 0 secret inventory grouped `post-pr-retrospective.yml` with the head-defined `pull_request` consumers and prescribed the same base-ref environment restriction. Its only pull request trigger is `types: [closed]`. A close-triggered workflow runs after the merge, so a workflow edit that merges becomes the base, and restricting the environment to the base ref hands the secret to exactly the edit an attacker landed. The containment for that one is review on the workflow path, not scoping. The inventory was assembled by grepping for secret names and `pull_request`, which is why the trigger **type** never entered the grouping.

**An unimplementable fallback, offered as the safe option.** The approval-count item carried "or scope the count to the enforcement paths CODEOWNERS covers" as its fallback when no independent approval producer exists. A ruleset targets refs, not paths, so `required_approving_review_count` cannot be path-scoped, and CODEOWNERS decides who approves rather than how many. The fallback was the more conservative-sounding branch and it does not exist. Removed rather than reworded: there is no path-scoped approval count in GitHub to point at.

**The behavioral cost was recoverable from the tree the whole time.** Six rounds of panel review and eleven bot reviews all reasoned about the size ceilings from GitHub label populations, and every one of them accepted the same limitation: that pull requests the ceiling deterred, split, or squashed leave no artifact a query can reach. That was true of GitHub and false of this repository. `grep` over `.agents/qa/`, `.agents/sessions/`, and `.agents/retrospective/` returns eight recorded workarounds across seven months, including two squashes on PR #5178 that made eleven cited review SHAs unreachable, a `main` merge on PR #4954 performed for no purpose except to buy ceiling headroom, and a review finding on that same pull request left unfixed because the commit budget was spent. ADR-100 now carries them. Worth recording as a review failure rather than a finding: the repository's own protocol requires agents to write down what they did, which makes it a searchable corpus of exactly the evidence every reviewer had agreed was unobtainable, and nobody searched it.

**The commit ceiling has two enforcement sites and the decision named neither.** A bot reviewer found that `pr_commit_count.py` already returns 0 in every case, so ADR-100's original item 1, "`pr_commit_count.py` stops blocking," would have retired nothing. The CI block is `enforce_pr_validation.py:64-84`. Checking that also surfaced a second site the review had not touched at all: `_check_commit_limit` in `git_hook_policy.py`, reached from the pre-push hook, which counts total commits including merges rather than authored non-merge commits and carries two reliefs the CI path lacks. That is the gate every recorded workaround actually hit, because it blocks the push rather than the merge.

Two claims were withdrawn after checking, which is recorded because the corrections matter as much as the findings.

- Critic's round-1 claim that ADR-021 mandates cross-vendor review panels was overstated and withdrawn in round 3. `AI-REVIEW-MODEL-POLICY.md` mandates explicit per-job model routing and forbids PASS under insufficient evidence. It does not require cross-vendor panels. Nothing binds subagent panel composition.
- The orchestrator's claim that Phase 0 was blocked by a 403 was wrong, corrected by architect in round 3.

The panel is single-vendor: all six roles pin Anthropic models. That is recorded in ADR-101 as accepted residual risk rather than solved, and it is the sharpest limitation on how much this debate's own agreement should be weighted.

## Unresolved and deliberately deferred

- **The debate mandate's catch rate is unmeasured.** Independent-thinker's condition, that the oversight mechanism be measured rather than assumed, was originally filed as blocking completion of ADR-101 Phase 2 rather than its start, and independent-thinker flagged in round 4 that this permits opening Phase 2 with the deciding number unmeasured. **Superseded in round 5**: high-level-advisor required the go/no-go be flipped to default-abandon, so an unpublished catch rate now blocks Phase 2 from opening at all. The ADR and this log agree on the default-no disposition; the round-4 wording above is retained only as the position it replaced.
- **ADR-100's blocking-value evidence was an n of 1 until the population was enumerated.** A bot reviewer supplied the query the panel believed did not exist. Seven closed-unmerged `needs-split` pull requests exist in the window; exactly one carries `commit-limit-bypass`, and it was independently failing its own security gate. **Closed in round 6**: all seven were characterized. #4814 (13 commits) and #4733 (11 commits) were the last two, both under the effective ceiling and neither carrying the bypass label. Because #4846 carried the bypass, meaning relief was granted, the enumerated population contains no pull request the blocking ceiling actually stopped. Survivorship remains the one open limitation: pull requests the ceiling deterred appear in no query.
- **Tag protection** and the `BOT_PAT` scope question (whether reducing below classic `repo` conflicts with minting real-user reviews) are Phase 0 inventory work.

## Between rounds: the base moved under the conclusions

Not a debate round. Recorded here because it changed cited facts after the panel had finished, and because the mechanism generalizes.

Minutes after the pull request opened, the owner merged `main` into the branch. That merge carried PR #5179, "remove session, session-init, session-end, session-log-fixer skills and session protocol," which deleted `.agents/SESSION-PROTOCOL.md`.

ADR-101 cited that file as a live six-agent debate trigger, in the PR #5177 incident and in the description of what the mandate covers. The same merge moved `check_adr_review_policy` from line 1390 to 1382, moved the `skip: merge` entry from lines 199-200 to 198-199, and shifted governance MUST-1 from line 12 to 13. Every one of those was verified true when written and false forty minutes later.

Every citation in both documents was re-run against the merged tree. Six held unchanged. Five were corrected. One finding was substantive rather than cosmetic: the trigger set has already narrowed to ADR files alone, which is a partial move toward what ADR-101's Application A proposes, so the ADR now says that instead of proposing it as though nothing had happened. The PR #5177 evidence survives the deletion, because what failed there was that a session could decline the mandated review and still commit, and removing one path from the trigger set does not touch that.

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
- **The enumeration's inference was invalid.** `commit-limit-bypass` marks relief granted, not the blocking threshold being reached. #4821 has 29 commits and no label, which is exactly the counterexample class the enumeration was meant to rule out. Two of seven remain unread and the label cannot clear them, so ADR-100 now says the population check is incomplete rather than closed.
- **A cited convention does not exist.** Both ADRs claimed one-idea-per-commit is documented in `.claude/rules/universal.md`. A search returns nothing; MUST-6 is the five-file rule being retired. Nothing survives the retirement, and the text now says so.

### The observation worth keeping

Every round-5 correction originated in bot review of the live pull request, not in the agent panel. The panel had converged to Accept twice on text containing a closed issue described as a live CVSS 8.8, a spoofable anchor, an invalid inference, and a citation to a rule that does not exist.

All six panel roles pin Anthropic models. This is what the single-vendor limitation recorded in ADR-101 predicts, observed rather than theorized, and it is the strongest evidence in this log for why cross-vendor review belongs in the design rather than in a follow-up. It is also the reason the panel's own agreement should be weighted below the external findings it missed.

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

Both are recorded here because closing on the vendor explanation would foreclose a question the cheaper fix answers, and because the falsification harness ADR-101 already defers is the instrument that would settle it. Analyst's round-6 pass is weak evidence for the second hypothesis: given an explicit mandate to re-verify numbers against the tree, it checked every countable figure and found them all correct.

### The gap the council did not find

After the council decision was recorded, external review found one more, and it is the sharpest evidence-design finding of the whole exercise: **the enumeration had classified only closed-unmerged pull requests.** A pull request the ceiling is currently holding is open, not closed, so the population most likely to contain a counterexample had never been queried.

Six roles had reviewed that enumeration across two rounds. Analyst, whose explicit mandate was evidence adequacy, had pressed hard on sample size and on the two unread cases, and did not raise the missing population. Neither did the orchestrator who built it.

Classifying the open set returned three at the 18:00Z cutoff, excluding this decision's own pull request, which was opened at 18:05:08Z and does not belong in the evidence set that argues for it. A first attempt used a later snapshot and mixed the two, and it also repeated the very inference this decision had already withdrawn: it read the absence of `commit-limit-bypass` on #5176 and #5181 as proof they were advisory-tier, when that label marks relief not granted rather than the threshold not reached. A second reviewer caught the repeat. Measured properly, #5176 carried 24 authored non-merge commits at the cutoff against a relieved ceiling of 40, and has since grown to 40 against that same 40, one commit from blocking. The finding survived, on evidence that had not existed when the council voted for it and after the same error was made twice.

That is worth recording plainly. The conclusion was right and the reasoning behind it was incomplete, which is the condition a review process exists to detect and this one did not.

### Two more after the decision, both about how a claim was scoped

Neither changed a conclusion; both changed what the text was entitled to say, and they are recorded because the pattern is the same one that runs through this whole log.

**A pinned cutoff that could not contain its own population.** The counts carry a stated snapshot of 18:00Z. The open-population table was written under that attribution and could not have been: #5181 was opened at 18:05:08Z, five minutes after the cutoff it was filed under. A first repair stated both timestamps side by side, which was honest but left a headline figure spanning two snapshots. The second repair is the right one: evaluate every query at the one cutoff and drop #5181, which does not belong in its own evidence set regardless of timing. Pinning a timestamp was itself a correction from an earlier round; pinning it and then filing later evidence under it is the same error one level down.

**A threat-model claim that contradicted its own remedy.** ADR-101 asserted that a ruleset matches a required check by context name only, and two paragraphs later proposed pinning `integration_id` as the fix for the spoofing hole that claim describes. Both cannot be unconditionally true. The claim holds for this repository's configuration, where `scripts/ci/ruleset_required_contexts.py` pins names alone, and not for GitHub in general. Scoped in both places.

A third, found in the same pass and sharper than either: enabling `require_code_owner_review` over enforcement paths would deadlock rather than gate. All five CODEOWNERS entries name the repository owner, the loop's pull requests are authored by that account, and GitHub forbids self-approval, so the rule would leave no eligible approver for exactly the changes it governs. The ADR now carries that as a Phase 0 prerequisite.

The shape recurs across all of these: a statement true of a measured instance, written as though true of the mechanism. Reading a label's absence as proof of a threshold, citing a rule whose path scope does not reach the file, asserting a matching rule that the proposed fix contradicts, and assuming a review requirement has someone able to satisfy it. Four instances, one habit, and every one caught from outside the panel.

### Where the review ends

High-level-advisor's read, which the orchestrator accepts: freeze the text. Six rounds on six files, with the external reviewers out-yielding the panel, means another round buys marginal prose and spends credibility the panel needs. What remains is not more review; it is the owner's decision on these proposals, and then MUST-1 and MUST NOT 1 on the implementation pull requests that edit `.agents/governance/**`. Those rules do not gate this pull request, per the scope correction recorded at the top of this log.

## Verdicts

| Round | architect | critic | independent-thinker | security | analyst | high-level-advisor |
|---|---|---|---|---|---|---|
| 1, tier sketch | Block | Block | D&C | Block | Block | D&C |
| 2, single ADR | Block | Block | D&C | Block | Block | D&C |
| 3, split pair | D&C | Block on 098, D&C on 099 | D&C | Block | D&C | Accept |
| 4, revised | Accept | Accept both | Accept | Accept | not re-run | not re-run |
| 5, corrected | Accept | D&C | Accept | Accept | D&C | Accept |
| 6, final | Accept | D&C | D&C | D&C | Accept | Accept |
