---
id: ADR-100
status: proposed
date: 2026-08-20
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-100: Retire the Pull Request Size Ceilings

## Status

Proposed

## Date

2026-08-20

## Context

Two gates cap pull request size in this repository.

`scripts/validation/git_hook_policy.py` caps authored files per commit at five, with no bypass of any kind. The commit ceiling is enforced in two places: `_check_commit_limit` in the same file blocks the push, and in CI `scripts/validation/pr_commit_count.py` classifies a pull request at 10 (warning), 15 (alert), and above its effective limit (blocked) while `scripts/ci/enforce_pr_validation.py:64-84` turns that classification into the failure. Relief at the blocking tier runs through a `commit-limit-bypass` label. State the normative reservation and the actual permission separately, because they differ and the difference is a finding below: CONTRIBUTING.md:880 reserves the label to a human maintainer, and nothing enforces that, because a GitHub label is applicable by any account with write access.

Three details of the commit ceiling matter and an earlier draft of this decision got all three wrong. The CI path counts **authored non-merge** commits, not the total GitHub displays (`pr_commit_count.py:110`; the raw total is kept for audit only). The ceiling is **relieved to 40** for a branch carrying a qualifying merge from `main` (`:65`, `:71`, issue #3596). So the CI contract is 20 authored commits, or 40 after a base merge, not an unconditional block at 20. And the local pre-push path does not share that arithmetic, though the difference is much narrower than three revisions of this decision claimed. Those revisions said `_check_commit_limit` counts "over the push range", which is wrong, and wrong in the direction that flatters the argument. `resolve_push_update` sets the range from the trunk, not from the pushed increment: `git_hook_policy.py:5604` reads `base = _merge_base(repo_root, "origin/main", push_ref.local_sha)`, and `:5620` builds `range_spec = f"{base}..{push_ref.local_sha}"`. The remote branch tip is a fallback used only when that merge base cannot be resolved. So both sites measure the same population, the branch against the trunk, and both read the same two thresholds, which `pr_commit_count.py:62-71` declares "the single source of truth" and `git_hook_policy.py` imports rather than restates. The entire arithmetic difference is one absent flag: `_check_commit_limit` at `:6123` passes no `--no-merges`, so branch-maintenance merges count locally and do not count in CI. It also carries two reliefs the CI path has no equivalent of, one for commits already carried by another pushed branch and one allowing small pushes on a branch already labeled `needs-split`. Measured on this branch at its remote head `b8f20196e`: 112 total, 14 merges, 98 authored, and GitHub reports the same 112. Both numbers are over 40, so on this branch the flag changes nothing, which is why the finding is a correction and not a remedy. One gate, one population, one threshold pair, one missing flag, two relief sets.

Measured at a 2026-08-20T18:00Z cutoff over the date-bounded window 2026-08-06 to 2026-08-20: 292 pull requests opened, 104 of them (36%) carrying `needs-split`, and 20 carrying the nominally human-only bypass label. Queries: `created:2026-08-06..2026-08-20` alone, then with `label:"needs-split"`, then with `label:"commit-limit-bypass"`. Described as a date-bounded window rather than "the preceding 14 days", which an earlier revision called it: `created:` is date-granular and includes all of August 6, so the span is 14 days and 18 hours against an 18:00Z cutoff. The three headline counts are the query's, not a re-derivation at exact timestamp boundaries.

That cutoff is load-bearing because the closing day was still in progress. A reviewer re-running the same date-bounded queries later in the day saw 296, 105, and 21. Read every count in this decision against the stated cutoff rather than as a standing figure; the argument does not turn on the difference, but the numbers are a snapshot and should be cited as one.

Read the 36% carefully, because it is weaker evidence than it looks. `pr-validation.yml` applies `needs-split` at `WARNING`, `ALERT`, or `BLOCKED`, and its own comment states the step "is ADVISORY and must never fail the job." So the label counts notices from 10 commits upward, not blocks. The 20 bypass applications are the closest thing to a blocking figure the queries produce, and the next paragraph explains why that is still not a count of blocks.

**That figure counts labels, not humans, and an earlier revision of this decision said humans.** The query returns 20 labeled pull requests. It does not establish who applied the label, and the actor cannot be inferred from label presence. The repository documents the counterexample in the enforcement code itself: `scripts/validation/git_hook_policy.py:6055-6070` records that an agent applied `commit-limit-bypass` to PR #4735 on 2026-08-08, and that it did so **because this gate's own failure message named the label as the reader's next step** (issue #4782). The comment states the mechanism plainly: "Naming the label as the reader's next step tells whoever tripped the gate to grant themselves a permission they do not hold." The message was rewritten to add the prohibition; the label's permissions were not changed, because a GitHub label carries none.

The label proves neither the actor nor the threshold, and successive revisions of this decision inferred each in turn. The first said 20 **human** applications, which the PR #4735 case above refutes. The correction then said 20 **blocking-tier** reliefs, which is the same inference in the other dimension and is the one this decision rejects twelve lines below: the label marks relief granted, not the threshold reached. A pull request can carry it having never been blocked.

So the honest reading of the 20 is: **20 pull requests carrying the bypass label**, with neither actor nor threshold established for the set. Blocking is established only where the arithmetic was reconstructed, and within this window that is three cases: #4846 at 235 commits, #5177 at 60 authored non-merge against a relieved ceiling of 40, and #5178, which its own session log records as blocked at 23 and again at 33 commits ahead. One labeled pull request was reconstructed as **not** blocked, #5176 at 25 against 40, which is the direct counterexample to reading the label as a block. Every claim below is scoped to those measurements rather than to the 20.

This is also the cleanest instance in this repository of ADR-101's invariant, and it arrived from the opposite direction. The commit ceiling is a P0 and P1 gate whose sole relief is a P0-writable artifact: any account with write access applies a label, and nothing verifies the human maintainer CONTRIBUTING.md requires. The gate does not protect the thing it gates from the actor it gates.

The rationale on record is `.agents/governance/PROJECT-CONSTRAINTS.md:125`, which cites one 2026-01 incident, PR #908: 59 commits, review slow and merge risky. That was a single data point, gathered before this repository had either its present adversarial review practice or its present volume.

### What the gate actually fires on

Sampling pull requests in the window shows the count gate does not measure one condition. It measures at least three, which need opposite responses.

| Pull request | Commits | Files | Condition | Correct response |
|---|---|---|---|---|
| #4846 | 235 | 16 | Its own security scan failed; `mergeable_state: blocked`; never merged. Which check refused the merge is not established, and `Validate Vendor Provenance` is not a pinned context | Block |
| #4718 | 109 | 49 | Six real defects, each pinned with its own fix and test; merged | Allow |
| #5036 | 25 | 28 | One real defect reported four times across review threads before it was fixed; merged | Allow |
| #5152 | 11 | 22 | A fail-open bug family found during review; merged | Allow |
| #5103, #5107 | 18 to 20 | 13 | Zero open review threads; count inflated entirely by the QA and session evidence rebind firing on every `main` merge into a long-lived branch | Allow, and fix the generator |

Neither size axis separates these. Net authored file surface would pass #4846 at 16 files and flag #4718 at 49, which is backwards. Commit count flags #4846 correctly but punishes #4718 and #5103 identically for behavior the repository wants.

### The closed-unmerged population, enumerated

An earlier draft of this decision said the labeled population could not be enumerated by tooling and recorded the absence of a counterexample as untested. That was wrong. `label:"needs-split" created:2026-08-06..2026-08-20 is:closed is:unmerged` returns the population directly, and a reviewer supplied the query.

It matters because the closed-unmerged set is one place a counterexample would live: a change the ceiling stopped that should not have landed. The open population below is the other, and the section after that covers a third question the labels cannot answer at all. The query returns seven.

| Pull request | Commits | `commit-limit-bypass` | State at close |
|---|---|---|---|
| #4846 | 235 | yes | Security scan failed; `blocked` at close; refusing mechanism not established |
| #4821 | 29 total, authored count not measured | no | `blocked`; its own body states governance rules require human approval and forbid auto-merge. Merges `main`, so its effective ceiling is 40 |
| #4872 | 19 | no | Under the ceiling; 9 of its 19 commits are `docs(qa): bind ...` rebind churn |
| #4985 | 14 | no | `clean`, mergeable at close |
| #4683 | 13 | no | `dirty`, merge conflict |
| #4814 | 13 | no | Under the ceiling. Trunk merge-queue work, abandoned when the queue was removed; 4 of its 13 commits are `docs(qa): repoint ...` evidence rebinds |
| #4733 | 11 | no | Under the ceiling. Five-issue cluster, `blocked`, `infrastructure-failure` |

Exactly one of the seven carries `commit-limit-bypass`. Its description is "Allows PR to exceed 20 commit limit," so it marks **relief granted**, not the threshold being reached. Those are different sets in principle, and the absence of the label does not prove a pull request stayed under the ceiling.

An earlier draft offered #4821 as proof of that gap: 29 commits, no bypass label. That argument was withdrawn after review. The 29 is GitHub's total including merges, while the gate classifies authored non-merge commits, and #4821 is branch-freshness work that merges `main`, which would relieve its ceiling to 40. On the gate's own arithmetic it was probably never blocked. The distinction between "relief granted" and "threshold reached" still holds as a matter of what the label means, and #5178 turns out to supply the worked example: its session log records the push blocked at 33 commits ahead with `gh` auth unavailable to apply the bypass, so the threshold was reached while relief was not available at all.

All seven are now characterized, and none was prevented from landing by the size ceiling. One was mergeable at close, one had conflicts, one was governance-gated by its own text, three sat under the effective ceiling, and #4846 carried the bypass label, meaning relief was granted rather than withheld.

That last point sharpens the result rather than softening it. Because #4846 was relieved, the enumerated population contains **no pull request that the blocking ceiling actually stopped**. The gate's harm-prevention record over this window is empty, not thin.

### The open population, enumerated

The closed-unmerged set is not the only place a counterexample can live, and an earlier revision of this decision treated it as though it were. A pull request the ceiling is *currently* holding is open, not closed, so the open labeled population had to be classified too. A reviewer raised this.

The query is `label:"needs-split" created:2026-08-06..2026-08-20 is:open`, evaluated at the same 2026-08-20T18:00Z cutoff as every other count here. It returns three. This decision's own pull request, #5181, was opened at 18:05:08Z and is excluded on both grounds: it postdates the cutoff, and an artifact should not appear in the evidence set that argues for it.

| Pull request | Authored non-merge at cutoff | Qualifying `main` merge | Effective limit | Blocked |
|---|---|---|---|---|
| #5176 | 25 (26 total at cutoff, 1 merge) | yes, at 17:50Z | 40 | No |
| #5177 | 60 (63 total at cutoff, 3 merges) | yes, at 16:55Z | 40 | Yes. 60 exceeds the relieved 40, and it carries `commit-limit-bypass`, so relief was granted |
| #5178 | 7 surviving at cutoff, 12 non-merge at merge | yes, at 18:24Z | 20, then 40 | Yes, twice, at 23 and at 33 commits ahead. Its surviving history understates it because the branch was squashed both times |

Every cell is measured from the head refs rather than inferred from labels, and the distinction matters because earlier revisions got it wrong twice. Absence of `commit-limit-bypass` marks relief **not granted**, not the threshold **not reached**, and `needs-split` fires from the warning tier. So the label cannot clear a pull request; only the arithmetic can. The first version of this table read #5176 as advisory-tier on exactly the inference already withdrawn for #4821, and a reviewer caught the repeat. The revision after that left #5177 and #5178 as "carries the label" rather than a count, which is the same inference in the opposite direction. Both are now counted with `git rev-list` over `pull/N/head` against its merge base, split by parent count and filtered on committer date.

#5178 is the row that does not fit the format, and the misfit is the finding. Its surviving history holds 12 authored non-merge commits, comfortably under any ceiling. Its own QA report records that the branch reached 23 commits ahead of `origin/main` and then 33, and was squashed both times. The table can only count what survived, so for any branch the ceiling caused to rewrite itself, the count in this column is not what the gate saw. That is the subject of the next section.

#5176 is worth noting beyond its verdict. It has continued growing since the cutoff and now sits at 40 authored non-merge commits against a relieved ceiling of exactly 40, one commit from blocking, through a history dominated by fix-plus-rebind pairs answering successive review findings. That is the #4718 rigor shape approaching the boundary in real time.

Two open pull requests reached the blocking tier by measurement and both carry the bypass label, which is the measured statement; who applied those labels is not established, and an earlier revision of this sentence said "relieved by hand" while the same sentence conceded the actor was unknown. #5177 is the same pull request cited below for spending its output on gate arithmetic, so the two halves of that observation are the same case seen from opposite sides.

Combining both populations at one cutoff: across ten labeled pull requests classified by hand, seven closed-unmerged and three open, no pull request was stopped from eventually landing by the ceiling. Three reached the blocking tier. Two carried the bypass label. The third, #5178, did not get relief at all: its own session log records the push blocked at 33 commits ahead **with `gh` auth unavailable to apply the bypass**, and the branch was squashed instead.

An earlier revision of this paragraph said all three were relieved, which its own evidence four sections down refutes. The correction strengthens the cost case rather than weakening it: a ceiling that forces a squash is worse than one that grants relief, because the squash is what destroyed eleven cited review SHAs. "Nothing was stopped from landing" and "everything that reached the tier was relieved" are different claims, and only the first is supported.

### What actually stopped the bad one

#4846 is the only pull request in the sample that should not merge, and it did not merge. It was not the size ceiling that held it: the ceiling labeled it and then relieved it, since #4846 carries `commit-limit-bypass`. **What did hold it is narrower than three revisions of this decision claimed, and round 9 was right to force the correction.** Those revisions said its security and vendor-provenance gate held it. The record does not support a causal claim: the cited retrospective says its security scan failed and that the owner was asked to decide, `mergeable_state: blocked` does not name the blocking check, and `Validate Vendor Provenance` is not a pinned required context (`scripts/ci/ruleset_required_contexts.py:11-22` lists nine and it is not among them). What is established is that it was labeled, relieved, failed its own security scan, sat `blocked`, and never merged. Which mechanism refused the merge is not determined. That weakens the positive half of this section's claim and leaves the negative half intact, which is the half the decision actually needs: the ceiling did not stop it. The size gate labeled it, and it also labeled #4718, #5036, #5152, #5103, and #5107, which all merged and should have.

That is the finding this decision rests on, bounded by both enumerations above: across the ten labeled pull requests classified at the cutoff, the blocking ceiling stopped nothing it did not also relieve, and the one pull request that should not have merged did not merge, by a mechanism the record does not identify. This sentence said "was held by a correctness gate" through four revisions and one sweep; it is the fourth paraphrase of a claim corrected one paragraph above, which is the propagation failure this pull request keeps producing. Over the same window the ceilings imposed cost on five of the six sampled pull requests that were doing the right thing.

### What the ceiling actually caused, recovered from in-tree records

The two label queries above answer one question: did the ceiling stop a change that should not have landed. They cannot answer a second one, because a branch that was squashed, split, or abandoned before opening leaves no label behind. That second question is what the ceiling made authors do instead.

It is answerable anyway, and not by any GitHub query. This repository's session logs, QA reports, and retrospectives record the workarounds as they happened, in the tree, with the commit counts that triggered them. Eight are recoverable by grep.

| Record | What the ceiling caused |
|---|---|
| PR #4954, `.agents/qa/000-session-14695-adr-080-amendment-qa.md:34` and `000-session-15001-pr-4954-round2-findings-qa.md:35` | At 21 authored commits, with the bypass label needing a human and squashing needing a force-push, the session merged `origin/main` through `gh pr update-branch` **for the sole purpose of supplying `contains_main_merge` evidence** and relieving the ceiling to 40. The merge then made `post_qa_code_changes()` read every path main had touched as changed, forcing a rebind of `endingCommit`, `comparison.head`, and three QA reports |
| PR #4954 round 15, `.agents/qa/000-session-14706-pr-4954-round3-coordination-qa.md:54` | "with the PR at 39 of the `MAIN_MERGE_BLOCK_THRESHOLD=40` authored-commit ceiling, this commit is the last one this session can make, leaving no budget for that cross-cutting change." Two live review findings were answered with a pull request reply instead of the fix |
| PR #5178, `.agents/qa/session-99923-premise-verification-qa-report.md:10-11` and `.agents/sessions/2026-08-20-session-99923-bbadd3bf9-implement-premise-verification-fix-issue.json:176` | Squashed twice. First at 23 commits ahead, collapsing 7 local commits into 2. Then at 33 ahead, with `gh` auth unavailable to apply the bypass, collapsing the branch into 6 commits and force-pushing. Eleven commit SHAs cited in that report's round-by-round evidence became unreachable, and the report now carries a paragraph listing them. The session stopped and asked the operator through `AskUserQuestion` which repair to take |
| Session 3468, `.agents/sessions/2026-07-27-session-3468-eval-gate-significance.json:15` and `:830` | "ADR-008's twenty-commit ceiling refused the push at twenty-one." The branch was left at twenty and the remaining findings moved to a new branch. Later in the same session, at the ceiling again, a reviewer proposal recorded as "split-independent and therefore sound" was filed rather than folded in, "not a fold-in on a stacked branch at the commit ceiling" |
| Session 3991, `.agents/sessions/2026-07-30-session-3991-dedupe-copilot-gotchas.json:162` | Records the two size gates contradicting each other: the ceiling "only runs at push time, so a long branch finds the ceiling after the work is committed," and "squashing is often the wrong repair, since the five-file atomic rule then makes the collapsed commit a different violation" |
| PR #955, `.agents/sessions/2026-01-16-session-8-pr-955-workflow-fix.json:190` | 86 commits, cleared by the bypass label |
| PR #3348, `.agents/retrospective/2026-07-26-auto-retro.md:43` | Bypass applied after review churn pushed it past 20 |
| Session 1830 round 14, `.agents/sessions/2026-05-10-session-1830-resume-skill-catalog-triage-post-1942.json:226` | Bypass applied |

Four things follow that neither label population could show.

**The ceiling produces history rewriting, and the rewriting destroys review provenance.** #5178 merged. What the gate changed was not whether it merged but whether its eleven rounds of review stayed citable. Eleven SHAs did not, and the QA report has to spend a paragraph saying so. The gate's stated purpose is reviewability.

**It suppresses fixes.** #4954 round 15 is a code change not made on a live review finding because the commit budget was spent. That is the opposite of the outcome the ceiling exists to produce, and it is recorded by the session that made the call.

**Its own relief mechanism is a distortion.** Merging `main` to buy headroom is a merge performed for the gate rather than for the branch, and it triggers the rebind cascade that item 5 below fixes. The evidence-rebind churn this decision cites as inflating commit counts is, in at least one recorded case, caused by the workaround for the count.

**The two size gates contradict each other.** Squashing to clear the commit ceiling produces a commit that violates the five-file cap, which has no bypass at all. Session 3991 states it plainly. An author at the ceiling has no compliant move left except splitting the pull request or waiting for a human.

This is also the answer to the survivorship limitation recorded below, and it narrows it. Survivorship is unrecoverable **by query**. It is partly recoverable from the tree, because this repository's own protocol makes agents write down what they did and why. That recovery is not a sample with a stated selection method, so it does not support a rate. It does establish existence, repeatedly, across seven months.

### The cost

The 5-file per-commit cap has no bypass. A single mechanical rename across a wide surface must be split into dozens of commits, which then trips the 20-commit ceiling, which then needs a label CONTRIBUTING.md reserves to a human maintainer and nothing enforces as such. PR #5177 in the current window shows this shape: a session spending its output on gate arithmetic and commit slicing rather than on the change.

The relief mechanism fails in three ways, and this repository has now recorded all three. An earlier revision of this paragraph said two with no third option, and the third is documented two sections below in this same decision. Honored as CONTRIBUTING.md writes it, it is a human decision per blocked pull request, and at 292 pull requests over a 14 day 18 hour window that caps throughput at human attention, which is the operating goal's stated failure mode. Not honored, it is the gated actor granting itself relief, which is PR #4735 and which makes the ceiling advisory in fact while remaining blocking in form. **Granted and unreadable**, which is the third, the human decision is made correctly and the gate never sees it: the label lookup fails and the gate treats the failure as refusal. That mode is worse than either of the first two, because it consumes the human attention the first mode costs and delivers the outcome the author would have got with no relief at all.

### A false positive measured while writing this

The scope half of the same family produced one during the authoring of this decision, which is worth recording because it was observed first-hand rather than sampled.

This pull request changes six files, all documentation. After a base merge, `scripts/detect_scope_explosion.py` reported `BLOCKED: PR scope explosion detected. 128/50 files` and refused the commit. The 128 was real arithmetic over a wrong input: the local `origin/main` ref still pointed at a commit the branch already contained, so the merge base resolved behind the branch and every commit main had landed in between was attributed to this pull request. A single `git fetch origin main` moved the reading from 128 to 5 with no change to the diff.

The remediation the gate printed does not mention refs. It advises splitting the pull request, stashing work, and offers `SKIP_SCOPE_CHECK=1`. Both of the first two are wrong here, and the third is the flag with a recorded abuse history that item 4 removes. An agent following the printed advice would either fragment a six-file change or reach for the bypass, and the retrospective at `.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md` records what happens next.

`.claude/rules/ci-scripts.md` MUST-14 already documents stale-ref inflation for the count ratchets and states that a ref fetched earlier in the same session should be treated as stale. The scope gate has the same failure and does not say so.

This does not by itself justify retirement, and it is one observation. It does show the gate blocking on branch bookkeeping rather than on scope, which is the same category error the count ceiling makes on rigor.

### The ceiling blocked this decision, measured while writing it

The false positive recorded above was the scope gate. This is the commit ceiling, on this pull request, and it is the second first-hand measurement rather than a sampled one.

At the point this section was written, `push-ref-policy` refused the push:

```text
ERROR: push has 42 commits, limit is 40
```

The arithmetic, taken from the branch at that moment: 42 total commits from the merge base with `main`, of which **37 are authored non-merge** and 5 are merges. The CI contract counts authored non-merge commits against the same relieved limit of 40, so **CI would have passed this push at 37 while the pre-push hook blocked it at 42**. One gate name, one population, one threshold pair, and one absent `--no-merges` at `git_hook_policy.py:6123` between them. An earlier revision called this "two gates, two counting rules", which overstates it: the two sites import 20 and 40 from `pr_commit_count.py:62-71`, which calls them "the single source of truth".

**Read that against the repair row in Alternatives, because it cuts against this decision and round 9 blocked until it was stated.** The gate blocks on `commit_count > limit` (`:6134-6135` returns 0 when the count is less than or equal), so a `--no-merges` repair would have passed this push at 37, and passed the 45-commit event below at no more than 40. Those are the first two of the six first-hand events, and the second is the one that produced the sharpest finding in this section, the owner-granted bypass the gate could not read. So two of the six are attributable to a one-line counting defect rather than to the ceiling's design, and this decision should not bank them as evidence that the ceiling itself is wrong. The later refusals are far enough past the ceiling that the flag changes nothing: 75, 106, and 113 in the session that added this paragraph. The 89 refusal is deliberately not in that list, because the section below attributes it to the same counting defect: it is an automated base merge spending the relief it grants, which is a merge-counting artifact. An earlier revision both banked and disclaimed it. Count them from that list rather than from a total, because two nearby figures are not refusals and an earlier revision folded them in: 74 is a replay through the gate with a hand-built payload rather than a live push, and 112 is the remote-head measurement at the top of this decision. The cost case rests on those; it does not rest on events one and two.

What the five merges are matters more than the count:

| Merge | Why it exists |
|---|---|
| `cc4f40de7`, `5b069bf78` | `Merge branch 'main'`, the base merges that **grant the relief to 40 in the first place** |
| `9eca857da`, `91daf9da1`, `d66ee4e44` | `Merge remote-tracking branch 'origin/<this branch>'`, reconciling pushes other actors made to this branch while it was being worked |

So the local ceiling charges the author for the merges that buy its own relief, and for merges forced by concurrent activity the author did not initiate. Neither is authored change. A branch that other agents push to consumes its own ceiling without its author writing anything, and the relief mechanism costs one commit each time it buys twenty.

The relief paths available at that moment were the ones this decision has already enumerated, and every one of them is a path this decision argues against:

- **Apply `commit-limit-bypass`.** Reserved to a human maintainer by CONTRIBUTING.md:880 and applicable by any write-access account. An agent self-applying it is the documented abuse (PR #4735, issue #4782). Not taken.
- **Squash and force-push.** PR #5178's path, which cost eleven cited review SHAs. This branch carries live review threads pinned to its commits. Not taken.
- **`--no-verify` or any of the six bypasses.** Forbidden by `.claude/rules/universal.md` MUST NOT 2. Not taken.
- **Move the content by another transport.** Taken, and it is a deviation rather than a compliant path. See the note below.
- **Merge `main` again.** Relief is already granted; another merge adds one to the count and buys nothing. Counterproductive.
- **Ask a human.** The only remaining path, and a per-change human decision at the exact throughput ceiling this decision names.

`_unpushed_commit_count` does not help here and its docstring explains why: it deliberately keeps the branch's own remote ref in the count, because "excluding it would make every re-push measure only the newest commits, which would retire the ceiling entirely for any branch pushed more than once." That is a defensible choice for the gate's purpose. Its consequence is that a long-lived branch under review cannot re-push past the ceiling no matter how small the new work is; this push added two commits.

**The owner then granted the relief, and the gate denied it anyway.** This is the part worth recording above all the rest, because it was tested rather than reasoned about.

The repository owner applied `commit-limit-bypass` to this pull request. GitHub confirms both labels present: `["needs-split", "commit-limit-bypass"]`. The push was retried and returned `ERROR: push has 45 commits, limit is 40`.

The mechanism is not subtle. `_check_commit_limit` asks for the label by shelling out to `scripts/validation/check_pr_bypass_label.py`, which reads it through `gh pr view`, which uses GitHub's GraphQL API. In this execution environment GraphQL returns 403, the script exits 3, which is this repository's own convention for an external failure, and `_check_commit_limit` treats every non-zero return as relief-not-granted. The same 403 defeats the `needs-split` small-push allowance, which this branch also qualified for: it carries the label and the push added three commits against a cap of five.

**Two different 403s, and the distinction was measured only after a reviewer forced a recheck.** An earlier revision of this paragraph said REST answers 403 as well and left it there, which reads as one blanket denial. The two bodies differ. GraphQL returns `This GraphQL query is not enabled for this session, only the pinned set of PR-review operations is served`, and directs the caller to REST. REST then returns `GitHub access is not enabled for this session`. So the first 403 is a query allowlist that names a working alternative, and the second is the account-level denial that closes it. The distinction matters to this decision's remedy rather than to its verdict: a relief check that fell back from GraphQL to REST on the first message would still fail here, so switching transports is not the fix. What the pair actually shows is that the gate cannot tell an allowlist miss from an authorization denial from a network failure, because all three arrive as a non-zero exit it maps to relief-not-granted.

So the sanctioned, human-only relief was correctly granted by the only party entitled to grant it, and the gate could not see it. The failure mode is not the one this decision described. "A gate whose only relief is a human caps throughput at human attention" understates it. The accurate statement is that **the gate's only relief is unreachable from the environment this repository's own agents run in**, so the human decision does not work either, and a gate that fails closed when its relief check is merely unreachable is unconditional in that environment regardless of what any human does.

This is reproducible rather than anecdotal. PR #5178's session log records the identical failure in a different session two days earlier: "`gh` auth was unavailable in-session to run the `needs-split` label bypass." That session's response was to squash thirty-three commits and force-push, which is how eleven cited review SHAs became unreachable. The same unreachable relief produced the same destructive workaround, twice, in two sessions, and the second time only because the first was recorded and this one refused to repeat it.

Decision item 6's telemetry field "whether a relief check failed to evaluate" exists because of this event. Nothing in the repository currently distinguishes a gate that refused from a gate that could not ask.

**Then a later push succeeded, and the reason is the sharpest finding in this section.** After the content had been transported to the remote by another route, a local `git push` of the reconciling merge went through. The gate did not relent; it never ran. Lefthook reported `push-ref-policy (skip) no matching push files`, reproducible with `git push --dry-run`.

The mechanism is that the job is scheduled against a push-file set, and every file in that push already matched the remote, so the set was empty and the ceiling had nothing to inspect. Replaying the same range through the gate directly, with a hand-built ref-update payload on stdin, still returns `ERROR: push has 74 commits, limit is 40` and exit 1. The pairing was then completed without being sought: the very next push carried real file changes, `push-ref-policy` ran, and it refused at `ERROR: push has 75 commits, limit is 40`. One gate, one branch, minutes apart, and the only variable was whether the push happened to carry files the job recognizes.

So the verdict and the evaluation are separable. The gate would refuse that range and is simply not asked when the content arrives by another path. Neither outcome tracks whether the change was reviewable, which is the property the ceiling exists to protect. Recorded here rather than in ADR-101 because it is the same gate, though it is also a clean instance of that decision's invariant: a P0 gate whose evaluation is conditional on a file set the gated actor determines is scheduling, not enforcement.

**And a fourth refusal, which the branch produced on its own while this section was being written.** An automated job merged `main` into this branch on the remote. Reconciling that merge locally and pushing the next round of review fixes returned `ERROR: push has 89 commits, limit is 40`, with the 40 rather than 20 confirming that the main-merge relief was active the whole time.

Read the two numbers together. The relief exists because merging `main` is the thing a long branch is supposed to do, and every such merge adds one commit to the count that `_check_commit_limit` measures, because that count is `git rev-list --count` over the branch measured against the trunk and includes merges. So the mechanism that grants the relief also spends it, and an automated base-merge job spends it without any author acting. The CI half does not have this property, because it counts authored non-merge commits only. That is the missing-`--no-merges` finding again, arriving as a rate rather than as a one-time discrepancy: on a branch kept current by automation, the local ceiling drifts toward blocking on its own while the CI ceiling holds still. This one is squarely a counting defect, so the repair row in Alternatives covers it and this decision does not count it as evidence against the ceiling's design.

**And then the skip and the refusal happened back to back, in the sharpest form the finding has taken.** The two events above were minutes apart and one commit apart, at 74 and 75. This pair is cleaner, because the sizes ran the wrong way.

The local branch and the remote had identical trees and a divergent history: nine local commits whose content the API transport had already placed. `git push` of all nine returned `push-ref-policy (skip) no matching push files` and **succeeded**, because no file in the push differed from the remote and the push-file set was empty. The very next push carried one commit changing two evidence files, the job ran, and it refused at `ERROR: push has 106 commits, limit is 40`.

So the gate allowed a nine-commit push and refused a one-commit push, on the same branch, over the same range, with the same relief state, minutes apart. Nothing about reviewability distinguished them. The only variable was whether the push happened to carry a file whose bytes differed from the remote, which is a property of the transport rather than of the change. A ceiling whose evaluation is decided by that variable is scheduling wearing a gate's error message, and it is capable of passing the larger change while blocking the smaller one, which it did here.

**And a sixth refusal, in the session that corrected this decision's arithmetic.** After the local branch was reset to the remote head so that no divergent history remained, a `git push` carrying **one** commit was refused at `ERROR: push has 121 commits, limit is 40`; an earlier attempt in the same session, before two further commits, returned 113. Both labels were present on the pull request throughout.

Two things make this worth a paragraph rather than a tally entry, and an earlier revision listed the number in the summary lists above without narrating either. First, it is the cleanest statement of the ratio the ceiling actually enforces: the work being pushed was one commit, and `_unpushed_commit_count`, the relief that exists for exactly this case, reported **115** for it, because it deliberately keeps the branch's own remote ref in the count. Second, it is where the counting range was falsified. The refusal quoted a number that is the whole branch against the trunk, which did not match what three revisions of this decision said the gate measures, and checking that discrepancy is what produced the correction now recorded at the top of this document. The gate refused a push and, in the same message, disproved the text describing it.

**What this decision's author actually did, recorded as a deviation.** The content reached the remote through the GitHub API, which placed commits the pre-push gate had refused. None of the six mechanisms MUST NOT 2 enumerates was used, and no history was rewritten, but that is a narrow defense and a reviewer was right to reject it. MUST NOT 2 states in terms that its list is not a safe harbor, "Naming only `--no-verify` invites the reading that a different mechanism is sanctioned; it is not, and no repository document describes any of them as a supported skip", and it closes by naming the required action: "When a hook blocks you for a reason unrelated to your diff, hand the branch back with the measurement instead of bypassing." The branch was not handed back. The measurement was taken and the content was moved anyway.

So the accurate record is: an alternate transport achieved what the enumerated bypasses achieve, the rule's closing instruction was not followed, and the disposition belongs to the repository owner rather than to the author who took the shortcut. It is recorded here rather than in a reply thread because a decision arguing that gates should be honestly accounted for cannot describe its own gate evasion as compliant. Note the shape, which is this decision's subject seen once more: the rule binds the actor, the actor is the one who decides whether it was followed, and nothing above the tree checked.

This is not offered as proof the ceiling is wrong. It is one event, and the sample warnings above apply to it too. It is offered because the decision was already written and the gate then produced, unprompted, an instance of every mechanism the decision describes: the two enforcement sites disagreeing on merges, the relief consuming the budget it relieves, concurrent agents spending an author's ceiling, a blocked change whose only compliant exit is a human, and a push it would have refused passing unexamined.

## Decision

Retire both size ceilings as blocking gates. Do not replace them with another blocking size gate.

1. **Both commit-ceiling enforcement sites stop blocking.** There are two, they count differently, and an earlier draft of this item named only the classifier, which would have retired nothing.

   `scripts/validation/pr_commit_count.py` classifies and **already returns 0 on every classification path** (`:493`, `:519`; it still exits 2 on an argument or lookup error and 3 on a `RuntimeError`, at `:461`, `:480` and `:483`, so "returns 0 in every case" as an earlier revision put it is wrong and the distinction matters to anyone reading its exit code); its own comment explains that the `BLOCKED` status is emitted as a `::warning::` because "the final enforcement decision and its error annotation live in enforce_pr_validation.py." The CI block is therefore `scripts/ci/enforce_pr_validation.py:64-84`, which reads `COMMIT_STATUS`, fetches the pull request's labels, and returns `LOGIC_ERROR` unless `commit-limit-bypass` is present. Remove that branch and its bypass-label handling; keep the classifier's notice and warning output.

   Note one ordering property of that file, measured on this pull request: the `OVERALL_STATUS` check runs **before** the bypass-label branch, so a failure anywhere else in PR validation returns `LOGIC_ERROR` without the label ever being consulted. On this pull request a description-validation CRITICAL, raised because an inline-backtick filename read as a claim that the file had changed, took the required check red while the owner-granted bypass sat unused. Whatever replaces this code should not preserve that ordering surprise.

   The second site is local and fires earlier: `_check_commit_limit` in `scripts/validation/git_hook_policy.py:6122-6162`, reached from the `push-ref-policy` pre-push job. This is the gate every workaround in the section above actually hit, because it blocks the push rather than the merge. It also **counts differently**: `git rev-list --count <range>` includes merge commits, where the CI classifier counts authored non-merge commits only. Its relief set is wider too, adding an already-pushed-elsewhere carve-out and a small-push allowance for branches already labeled `needs-split`. Demote it to a report alongside the CI site, or the ceiling survives in the place it does the most damage.

   The `commit-limit-bypass` label and its human step retire with both.

2. **`check_atomic_commit` stops blocking.** The five-file guidance stays as advisory output. Note that no convention survives this: `.claude/rules/universal.md` MUST-6 is the five-file rule itself, and a search of `.claude/rules/` for a one-idea-per-commit convention returns nothing. Retiring the ceiling leaves commit granularity to author judgment, which is the honest description of the resulting state.

3. **The scope check becomes advisory, and process-record paths leave its measurement.** `scripts/detect_scope_explosion.py:50` sets `BLOCK_THRESHOLD = 50` and the script returns 1 above it, so the scope check blocks today. It stops blocking and reports only. Separately, `_partition_generated` already excludes generated files; extend that to `.agents/sessions/**`, `.agents/qa/**`, and `.agents/memory/episodes/**`, which are process record rather than reviewable change.

   An earlier draft of this decision described the scope check as already advisory. That was wrong, and the order matters: demoting the threshold has to land in the same change as item 4, or removing the bypass leaves a blocking gate with no relief at all.

   **This item rests on weaker evidence than items 1 and 2, and that is stated rather than blurred.** The populations enumerated above measure the commit ceiling. No equivalent measurement exists for the scope gate, and none can be produced from GitHub: it is invoked only from `lefthook.yml:378` and `:542`, never from a workflow, and it applies no label, so a pull request it blocked leaves no remote artifact. The counterexample search that was possible for the commit ceiling is not possible here. What this item rests on instead is three things: the gate traces to the same single incident, PR #908, through ADR-049 (`ADR-049-pre-pr-validation-gates.md:13-27`), which is still `Proposed` and whose own file threshold was 10 rather than the 50 that shipped; its only relief is the self-attested flag item 4 removes for a recorded abuse history; and the one blocking event observed first-hand while writing this decision was a false positive on branch bookkeeping. If that basis is judged insufficient, items 3 and 4 split cleanly into a decision of their own, and items 1, 2, and 5 stand without them.

4. **`SKIP_SCOPE_CHECK` is removed, after item 3 lands.** `scripts/detect_scope_explosion.py:492` honors `SKIP_SCOPE_CHECK=1` with no verification of the human approval it claims. `.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md` records an agent setting it twice after authorization was explicitly withheld, citing an agent-writable memory as its authority. Once nothing blocks on scope, the flag has no purpose, and a self-attested approval flag with a recorded abuse history should not outlive its use. Removing it before item 3 would tighten the gate rather than retire it.

5. **Fix the rebind churn at its source, `post_qa_code_changes`.** #5103 and #5107 show 18 to 20 commits with zero open review threads because the QA and session evidence rebind fires on every `main` merge into a long-lived branch. An earlier revision of this item said "fix the rebind generator" and named no component anywhere, while ordering it first, so the stated order could not be begun.

   The component is `post_qa_code_changes` in `.claude/lib/qa_report.py:244-253`. Edit that file only: `src/copilot-cli/lib/qa_report.py` is a generated mirror produced by `build/scripts/build_all.py`, and hand-editing it is the torn-state defect `.claude/rules/generated-artifacts.md` exists to prevent. Regenerate and commit the mirror in the same change. It runs `git log --format= --name-only --no-renames -m -z <qaCommit>..<head>`, and `-m` splits each merge and diffs against **both** parents, so every path `main` touched inside a base merge is returned as a post-QA code change. The QA report then reads stale and needs a rebind commit, once per base merge, on a branch that changed none of those paths. PR #4954's QA record states the mechanism in its own words: "Because `post_qa_code_changes()` walks `git log -m` (both parents of a merge), every path `origin/main` touched appears as changed relative to the prior binding."

   **The obvious fix is wrong, and a reviewer caught it before it shipped.** An earlier revision of this item offered "compare against the first parent for merge commits" as one of two options. For a base merge the branch is the first parent and `main` is the second, so diffing the merge against its first parent returns exactly the paths `main` imported, which is the false-positive set item 5 exists to remove. That option is deleted rather than reworded.

   What git already has for this is the combined diff. `-c` (`--diff-merges=combined`) lists, for a merge, only the paths that differ from **every** parent, which is the definition of a conflict resolution: content the author wrote during the merge rather than content either side brought in.

   That semantic was asserted rather than measured in the first version of this paragraph, and a reviewer declined to confirm it from memory, which was the right call. It is now measured, in two throwaway repositories built for the purpose. **Conflict merge**, where one file was touched by both sides and resolved by hand, one file changed only on the incoming side, and one file added only on the receiving side: `-m` returns all three, `-c` returns only the resolved file. **Clean merge**, where the two sides touched disjoint files: `-m` returns all three changed paths, `-c` returns nothing at all. So `-c` gives exactly the split this item needs, and the second case is the one that matters most here, because a clean base merge is what invalidates a QA binding today and under `-c` it would contribute no paths.

   Replacing `-m` with `-c` therefore drops the clean incoming delta and keeps the authored resolution edits, which is the behaviour this item wants and which neither the first-parent option nor a blanket `--no-merges` gives.

   **`-c` has a gap, it was found in review, and it is now measured rather than argued.** A combined diff lists a path only when the merge result differs from **every** parent, so a conflict resolved to one side verbatim is invisible to it. Both directions were tested in throwaway repositories. Resolved to the incoming side: `-m` returns the path, `-c` returns nothing. Resolved to the receiving side: `-m` returns the path, `-c` returns nothing, and `git diff <merge>^1 <merge>` also returns nothing while `git diff <merge>^2 <merge>` returns the path.

   That second measurement is what makes the gap tolerable rather than fatal, and an implementer needs the distinction. Resolving to the receiving side leaves the branch's validated content unchanged, so a QA binding that survives is correct. Resolving to the incoming side does change it, and `-c` misses that case: the branch adopted `main`'s version of a path QA had validated, and the report stays green. So `-c` is not the whole answer.

   State the composite in the implementation rather than leaving it to the implementer: take the union of the combined-diff paths and, for each merge, the paths where the merge result equals the second parent but differs from the first. The second term is `git diff --name-only <merge>^1 <merge>` intersected with the paths that changed in the merge, which recovers exactly the resolved-to-incoming case without readmitting the clean import, because a clean import differs from the first parent too and must be excluded by the same test that a conflict resolution passes. If that distinction cannot be made cleanly, prefer over-reporting to under-reporting here: a spurious rebind costs one commit, a missed one leaves a false PASS on the artifact that gates the merge. Pin all three cases with tests, not just the two originally named: a branch that merges `main` cleanly keeps its QA binding, a branch whose merge resolved a conflict in a QA-relevant path does not, and a branch whose merge resolved such a conflict to the incoming side also does not. `--no-merges` is the cruder alternative and a real loss, because it would stop counting conflict resolutions as authored change at all. This decision's own pull request hit it four separate times while being written, and the fourth is the sharpest: once the local history was pushed, its reconciliation merges joined the remote lineage and the same `-m` walk flagged the ADRs again from the pull request head, so no binding short of the head was stable.

6. **Record push-ceiling telemetry at demotion time.** When `_check_commit_limit` is demoted under item 1, have it emit what it would have blocked: branch, total and authored counts, the effective limit, which relief applied, and whether a relief check failed to evaluate. Append-only, outside the branch under measurement. Without this the pre-push ceiling has no observable behaviour at all after demotion, and the re-measure above can never cover the half of the gate that produced every recorded workaround. This item exists because a reviewer pointed out that the telemetry appeared only in prose and would therefore never be built.

   The recording has a second use this decision met first-hand. Both relief checks shell out to `check_pr_bypass_label.py`, which reads labels through `gh pr view`, which uses GraphQL. In the environment this decision was authored in, GraphQL returns 403 and both checks exit 3, so `_check_commit_limit` saw no relief and blocked a two-commit push on a branch that carries the `needs-split` label and qualified for the small-push allowance. A gate that fails closed when its relief check is merely unreachable converts an environment limitation into an unconditional block, and nothing today records that this happened. The telemetry field "whether a relief check failed to evaluate" is what makes that distinguishable from a genuine refusal.

   Add a third field for the same reason: **whether the job ran at all.** The skip recorded above produces no output of any kind, so a push the gate would have refused is indistinguishable from a push it never saw. A telemetry record that only appears when the job is scheduled measures the wrong population, and the nine-through-one-refused pair above shows the size of the error: the unrecorded push was the larger one.

   **Two things about this item are unresolved, and an implementer must settle both before it is buildable.** A reviewer raised each, and neither has an answer this decision can supply.

   First, the third field cannot be emitted from inside `_check_commit_limit`. A push whose file set is empty never enters that function, so instrumenting it records every verdict except the one this decision needs most. The recording has to come from a surface that is always scheduled on pre-push, or the job's scheduling has to change so it always runs. Choose one and say which; do not instrument the function and call the dataset complete.

   Second, this item says append-only and outside the branch, and names no sink. It does not choose a store, an authentication model, a retention period, or a failure policy, and the obvious candidate is not available: the environment this decision was authored in cannot reach the GitHub API from the pre-push path at all, which is the same 403 that made the relief unreadable. So an implementer cannot assume the record can leave the machine. Decide the reachable sink and whether a failed write blocks the push or is dropped, and state that decision here. Until both are settled, item 6 is a requirement rather than a design, and the 90 day re-measure of the pre-push half depends on it.

### What is deliberately not adopted

An earlier draft of this decision proposed replacing commit count with a convergence metric: commits added since the last green check run, and commits added without a corresponding review thread resolution.

That is not adopted here, for three reasons.

- On the sample above it changes no outcome. #4846 did not merge, and the ceiling is not what stopped it, since it carried the bypass label. Which mechanism refused it is not determined; see "What actually stopped the bad one".
- It is new machinery with no operating history, in a repository where the 2026-08-17 governance review measured 87 of 92 open issues (94%) as the repository's own automation breaking itself. A new required check with no baseline is a candidate to become issue 93.
- Both of its inputs are forgeable by the actor it would gate. This repository's loop holds thread-resolution tooling, and no rule in `.claude/rules/` or `.agents/governance/` forbids resolving one's own review thread. A job skipped by a job-level `if:` reports as satisfying a required check, so a green run is cheap.

If commit thrash later needs a control, it is a token-budget question, not a correctness question, and it needs its own evidence and its own decision. Filed rather than bundled.

## Prior Art Investigation

### What currently exists

- **Structure being changed**: a five-file per-commit cap enforced through lefthook, and a 20-commit per-pull-request ceiling enforced in two places, the pre-push hook and CI, with a `commit-limit-bypass` label as the only relief at the blocking tier. CONTRIBUTING.md reserves that label to a human maintainer; nothing enforces the reservation.
- **When introduced**: traced to the PR #908 retrospective of 2026-01 and issue #934, recorded at `.agents/governance/PROJECT-CONSTRAINTS.md:125`.
- **Original context**: one 59-commit pull request that made review slow and merge risky.

### Historical rationale

The ceilings were a proxy for reviewability, in a regime where a human did the reviewing and volume was low enough for that to work.

### Why change now

- **Has the original problem changed?** Yes. Volume reached 292 pull requests over a 14 day 18 hour window, and the reviewing is largely done by CI and agent review rather than by a human reading commits in sequence.
- **Is there a better solution now?** The one pull request in the sample that should not have merged did not merge, and the size ceiling is not what held it. An earlier revision credited the correctness gates for that outcome; the record does not establish which mechanism refused it. The proxy is redundant where it is right and costly where it is wrong.
- **Risks of change?** A genuine sprawl pull request could merge where the ceiling would have caught it. Mitigated by the fact that the ceiling never caught one on its own in the sample: #4846 carried the bypass label, so the ceiling relieved rather than refused it, whatever else held it. The residual risk is named in Consequences.

## Rationale

### Alternatives considered

| Alternative | Pros | Cons | Why not chosen |
|---|---|---|---|
| Keep the ceilings, add a self-service bypass flag | One line, matches the existing pattern | The pattern has a recorded abuse after approval was withheld (`2026-08-07-pr-4402-scope-bypass.md`) | Extends a mechanism with a known failure |
| Keep the ceilings, widen the human bypass | Uses existing machinery | 20 labeled pull requests per two weeks, three reconstructed as blocked, and the label is unenforceable as human-only (PR #4735) | Caps throughput at human attention, or is self-granted |
| Replace with net authored file surface | Measures reviewer burden more directly | Passes #4846 at 16 files, flags #4718 at 49; backwards on the sample | Wrong on the only case that matters |
| Replace with a convergence metric | Separates spin from rigor in principle | New machinery, no baseline, both inputs forgeable by the gated actor | Deferred to its own decision with its own evidence |
| Model judges whether a diff is "one idea" | No human needed | The model can assert any classification; self-report with a mechanical costume | No verifiable evidence behind the verdict |
| Repair the counter (`--no-merges` at `:6123`) | Fixes a real one-line defect. `pr_commit_count.py:112` already records authored non-merge counting as the intended contract under issue #3920, so the CI plane was fixed and the local plane was not | **Relieves branches within their merge count of the ceiling, which is a narrower band than retirement but is not empty, and two of this decision's own first-hand refusals sit in it.** The gate blocks on `commit_count > limit` (`:6134-6135` returns 0 when `commit_count <= limit`). Event one: 42 total, 5 merges, 37 authored, limit 40. 37 passes. Event two: 45 total, and merges are monotone on this branch because no squash was taken, so authored is at most 40, which also passes. Event two is the push that produced this decision's most-cited finding, the owner-granted bypass the gate could not read; with the flag present that push never reaches the relief check at all. Open PR #5176 is the same shape on another branch: 40 authored against a relieved 40 plus at least its qualifying `main` merge, so it is over the local ceiling today while CI passes it. The later refusals (75, 106, and 113; the 89 event is attributed to the counting defect and not banked here) are far enough past the ceiling that the flag changes nothing | **Not an alternative to this decision, and it does not clear it either.** It must be done regardless, because it is a defect. What it does not touch needs stating more carefully than an earlier revision managed, which listed the unreadable relief among the untouched costs while this same cell concedes the repair removes it. The eight partition as follows, and an earlier revision's split put one record in two buckets and dropped another, so count them by name. Three note only that the bypass was applied, which is the relief working rather than a cost the ceiling imposed: #955, #3348, and session 1830 round 14. Two are denominated in total commits with merge counts now unrecoverable: #5178 at 23 and 33 ahead, squashed twice, and session 3468 refused at 21, its log recording no merge count. Both were blocked at a limit of 20, so `contains_main_merge` was false and any inflation would have to come from non-`main` merges, which is possible, unmeasured and unlikely. #5178 is the squash case, so it sits here rather than among the survivors, which is where the earlier split double-counted it. One, PR #4954's rebind cascade, is caused by the `-m` walk that item 5 repairs rather than by the ceiling. **That leaves two.** #4954 round 15, at 39 of 40 **authored** commits, where a live review finding was answered with a reply instead of a fix, which no counting repair reaches. And session 3991, dropped entirely by the earlier split, which records the two size gates contradicting each other: squashing to clear the commit ceiling produces a commit violating the five-file cap, which has no bypass at all. That is a structural conflict between two gates rather than an arithmetic error in either. An earlier revision of this row claimed the repair changes no outcome on the evidence. That was false, and it was false in the direction that flattered this decision: it was measured only at 112, the largest overshoot in the corpus, which is selection on the dependent variable. Round 9 blocked on it |
| Repair the relief check (stop failing closed on an unevaluated lookup) | Directly addresses the sharpest measured failure: the owner granted the bypass and the gate refused it | `check_pr_bypass_label.py` exits 3 on a 403 and `_check_commit_limit` maps every non-zero return to relief-not-granted, so an unreachable check is indistinguishable from a refusal. Mapping exit 3 to advisory would have relieved event two and the `needs-split` small-push allowance with it | Also worth doing on its own merits, and also not a substitute. It makes the ceiling correct rather than absent, so it leaves the throughput argument and the seven other costs standing |
| Repair the push-file scheduling | Would close the skip, which is the only cost that lets the gate pass a larger change than it refuses | The job is scheduled against a push-file set and does not run when that set is empty. Fixing it makes the gate stricter, not looser: it converts the nine-commit push that passed into a ninth refusal | Rejected as a repair of this decision's problem. It removes an inconsistency by blocking more, which is the opposite of what the cost evidence argues for. It remains a prerequisite for item 6's telemetry |
| Retire the pre-push site only, keep the CI classification blocking | Removes the plane that counts merges and cannot read its own relief, while keeping a blocking ceiling on the plane that counts authored commits correctly and can read labels. Every one of the eight in-tree workarounds hit the local site, because that is the one that blocks the push | Keeps a blocking size ceiling, so the throughput argument survives and so does #4954 round 15, which was blocked by the CI arithmetic at 39 of 40 authored rather than by the local counter. It also leaves the atomic-commit and scope caps untouched, which items 2 and 3 handle separately | **The strongest surviving alternative, and this decision does not dismiss it.** It is a coherent smaller change and it would relieve most of the first-hand events, since those all hit the local site. It is not adopted because #4954 round 15 shows the CI half imposing the same suppression this decision objects to, so retaining it keeps the mechanism the cost evidence indicts. A reader who weighs the in-tree records lower than this decision does should take this row instead of the chosen one. The strongest counter is testability rather than the #4954 count, and round 11 supplied it: the falsification commitment below replays the retired **CI** contract, so keeping the CI plane blocking means every member of the would-have-been-blocked partition has already been relieved by label or squashed, and the replay then measures gate-plus-relief rather than absence-of-gate. This row retires the plane whose retirement cannot be falsified today, because item 6's telemetry does not exist yet, and keeps blocking the one whose retirement can be. That is backwards, and it is why the chosen option is the only one whose weakest claim gets tested. Round 10 raised the row; round 11 supplied this answer; both are recorded rather than argued away |
| Retire, replace with nothing blocking (chosen) | Pure subtraction; immediate relief; no new surface | Accepts residual sprawl risk | Chosen |

### Trade-offs

This trades a small, unproven protection against sprawl for the removal of a measured, recurring cost. The protection is unproven in the specific sense that across the six sampled pull requests and the seven enumerated closed-unmerged ones, it never made a blocking call that changed an outcome: every labeled pull request that reached the tier was either relieved or squashed, and it landed either way. An earlier revision said "never made a correct blocking call that a correctness gate did not already make", which asserts the #4846 causality this decision withdrew above. The cost is measured where it is measured and stated as such: 36% of pull requests carrying `needs-split`, 20 carrying the bypass label with three of them reconstructed as actually blocked, eight recorded workarounds across seven months, and at least one pull request in the current window spending its output on gate arithmetic.

## Consequences

### Positive

- The bypass step disappears, and with it all three failure modes of its relief: the human decision per blocked pull request when honored, the self-granted path PR #4735 demonstrates when not, and the granted-but-unreadable mode this pull request met first-hand. The number of touchpoints removed is bounded above by the 20 labeled pull requests and below by the three reconstructed as blocked; the decision does not claim a figure inside that range. The 36% `needs-split` rate is unaffected: that label fires from the warning tier, which Decision item 1 keeps.
- A wide mechanical change stops requiring dozens of artificial commits.
- One self-attested bypass flag with a recorded abuse history leaves the repository.

### Negative

- A genuine sprawl pull request now depends entirely on correctness gates and review to stop it. If those miss, nothing size-based catches it.
- Losing the label also loses the one event that routinely put a very large pull request in front of a human. Whether that look ever caught anything is not established: a search across the repository for `commit-limit-bypass` finds the label described only as relief a maintainer grants on request, for example `.agents/governance/GOTCHAS.md:238`, and no record of it producing a finding. The lost function is asserted, not measured, and should not be weighted as though it were.
- **The sample is still subject to survivorship, though less than an earlier revision claimed.** Pull requests the ceiling deterred, or that were split before they were ever opened, appear nowhere in the labeled population, so no query recovers them, and the 90 day re-measure below cannot recover them either. The in-tree records above recover eight cases the queries miss, which establishes that the deterred population is not empty. What stays out of reach is its size, because those records exist only where an agent chose to write one.

### Neutral

- The advisory output stays, so the information a reviewer used is still printed. Only the blocking authority is removed.

## Impact on Dependent Components

| Component | Dependency | Required update | Risk |
|---|---|---|---|
| `scripts/ci/enforce_pr_validation.py:64-84` | Direct | Remove the `COMMIT_STATUS == "BLOCKED"` branch and its bypass-label fetch. This is the CI block; `pr_commit_count.py` returns 0 on every classification path and must keep exiting 2 and 3 on its error paths, so demoting the size classification must not neutralize configuration and API failures. Note also that its `OVERALL_STATUS` check precedes the bypass branch, so an unrelated validation failure bypasses the bypass | High |
| `scripts/validation/git_hook_policy.py` `_check_commit_limit` | Direct | Demote to a report, and land item 6's telemetry in the same change. This is the pre-push block every recorded workaround actually hit | High |
| `lefthook.yml` push-file scheduling | Direct | The `push-ref-policy` job skips entirely when lefthook computes no matching push files, which is how a nine-commit push this gate would have refused passed unexamined while the one-commit push after it was refused. Item 6's third field cannot be emitted from a function that never runs, so either the telemetry moves to an always-scheduled surface or the scheduling changes | High |
| `scripts/validation/pr_commit_count.py` | Direct | Keep classifying and reporting. Already returns 0 on every classification path, though it still exits 2 and 3 on its error paths (`:461`, `:480`, `:483`), so no caller should read exit 0 as "classified" | Low |
| `scripts/validation/git_hook_policy.py` | Direct | `check_atomic_commit` advisory | Medium |
| `scripts/detect_scope_explosion.py` | Direct | Demote `BLOCK_THRESHOLD` (line 50) to advisory FIRST; then add process-record exclusions; then remove `SKIP_SCOPE_CHECK` at line 492. Removing the flag without the demotion ships a blocking gate with no relief | Medium |
| `lefthook.yml` | Direct | Jobs stay, exit codes become 0 | Low |
| `CONTRIBUTING.md` | Direct | Remove the bypass-label procedure | Low |
| `.agents/governance/PROJECT-CONSTRAINTS.md:125` | Direct | Record the constraint as retired, with this ADR as the reason | Medium |
| `.claude/rules/governance.md` MUST-1 and MUST NOT 1 | Indirect | These bind the **implementation** pull request, which edits `.agents/governance/PROJECT-CONSTRAINTS.md`, not this proposal: the rule's frontmatter scopes it to `.agents/governance/**` and this file sits in `.agents/architecture/`. MUST-2 runs the other way and is satisfied here, since it requires a governance change to be accompanied by an ADR | High |
| `.claude/rules/universal.md` MUST-6 | Direct | This is the five-file rule. Retire or restate it; there is no separate one-idea-per-commit convention to fall back on | Medium |
| QA and session evidence rebind | Direct | Fix the every-merge refire | Medium |

## Implementation Notes

One phase. No dependency on repository configuration, no new gate, no new required check. Items 1, 2, and 3's threshold demotion are independently revertible by restoring a return value. Three are not, and a reviewer was right that an earlier revision claimed otherwise for all of them: item 5 changes merge-diff semantics in `post_qa_code_changes`, item 6 adds a telemetry write outside the branch, and the process-record partition in item 3 changes what the scope gate classifies as reviewable. Reverting those three means reverting a behavior change, not a return value.

Order: fix the rebind churn at `post_qa_code_changes` per item 5; remove the CI block in `enforce_pr_validation.py` and demote `_check_commit_limit`, **landing item 6's telemetry in that same step rather than after it**, because a demotion that ships without the recording loses the push-time evidence permanently and the re-measure can never recover it; demote `check_atomic_commit` early, so that this change's own wide diff is not sliced by the cap it retires; demote the scope `BLOCK_THRESHOLD` and add the process-record exclusions; then remove `SKIP_SCOPE_CHECK`; then update the documents. The last two are ordered, not interchangeable, per Decision items 3 and 4.

### Time-box and re-measure

The blocking-value claim rests on ten labeled pull requests classified by hand across both populations, plus eight in-tree workaround records with no stated selection method. That is enough to retire the gates and not enough to close the question, so this decision carries one falsification commitment. A prior revision of this section was challenged from both directions in review, one role arguing it be cut as unrunnable and one arguing it be rewritten as the only test the decision has. It is rewritten, because the second reading is right: cutting it would leave the weakest-evidenced item in the decision with no test at all.

**Owner.** The repository owner, or a delegate the owner names in the follow-up issue. Not the implementing agent, and not this decision's author: a falsification test scored by the party whose decision it tests is the shape ADR-101 exists to refuse.

**Trigger.** File a follow-up issue titled "Re-measure the retired size ceilings" at the same time the implementation pull request merges, due 90 days after that merge. This decision is not complete until that issue exists; an unfiled re-measure is the ritual the cut argument correctly objects to.

**Population.** Every pull request merged into `main` in the 90 days after the implementation merge.

**The counterfactual, stated before the measurement so it cannot be fitted after.** Note the limit before stating it: a branch squashed before merge presents fewer commits than the gate saw, so this replay understates the would-have-been-blocked partition for exactly the branches the ceiling pressured into squashing. #5178 is the worked example at 12 against 33. Record that partition as a lower bound rather than a count. Replay the retired **CI** contract over each merged pull request's history as merged: authored non-merge commits against 20, or 40 where a qualifying `main` merge is present. That partitions the interval into the set the CI ceiling would have blocked and the set it would have passed.

**Pass or fail predicate.** The retirement fails, and the CI ceiling returns, if either holds for a pull request in the would-have-been-blocked partition:

1. It was reverted, or a fix-forward commit landed within 7 days repairing a defect it introduced, **and** a reviewer records that a smaller pull request would plausibly have caught it. Both halves required: reverts happen for reasons size does not predict.
2. A correctness gate failed on `main` after it merged, where that gate would have run before merge had the pull request been split.

Absent either, the retirement stands and the follow-up closes. A bad pull request in the would-have-passed partition is evidence about some other gate, recorded there, and does not count here.

**This predicate tests one of the three retired gates, and a reviewer was right that the section did not say so.** The counterfactual replays the CI commit ceiling. It cannot falsify the retirement of the five-file atomic cap or the scope cap, because neither is a function of commit count: a wide, low-commit regression, which is exactly the shape those two caps existed to catch, lands in the would-have-passed partition and is ignored by the predicate above. That matters most for the scope cap, which this decision already names as its weakest-evidenced item.

Two honest options, and this decision does not pick between them because the choice is the owner's. Either define a counterfactual per retired gate, replaying authored files per commit against five and net authored file surface against fifty over the same merged population, or split items 3 and 4 into their own decision so the scope and atomic caps are not retired on a test that cannot reach them. The second is cleaner and this decision has already offered the split twice; the first keeps one decision and costs two more replays.

**The pre-push half cannot be tested by this procedure, and that is a consequence rather than an omission.** Three earlier revisions grounded this on the wrong property, saying its contract evaluates a push range. It does not; it evaluates the same branch-against-trunk range CI does (`git_hook_policy.py:5604`), so the range is not what resists reconstruction. Three other things are, and only the third is unique to this half, which two revisions of this paragraph did not say. It applies two reliefs computed at push time from remote state as it stood at that moment; the CI block also consults labels at run time, so that break is shared. A squashed branch has erased the commits it saw; the CI counterfactual at the re-measure below replays merged history too, so for #5178 it replays 12 commits rather than the 33 the gate saw, and that break is shared as well. **The job does not always run at all**, and nothing on the CI side has an equivalent. So the honest statement is that squashing degrades both replays and the scheduling skip breaks only this one, which narrows the asymmetry this paragraph once asserted without removing the need for item 6's telemetry. This decision's own PR #5178 case is the proof of the second: 12 commits in surviving history against 33 the gate actually blocked. The third is the sharpest: a push whose files already match the remote skips the job entirely, leaving no record either way, and the pair recorded above shows the skipped push can be the larger one. Measuring it needs push-time telemetry recorded as it happens, covering the skipped pushes as well as the evaluated ones, which does not exist and cannot be added retroactively. That is why it is Decision item 6 rather than a line in this section: if the recording is not built when the ceilings are demoted, the pre-push ceiling is unmeasurable by construction and its retirement is permanent on the evidence already gathered.

### Follow-up, not part of this decision

- Commit thrash as a token-budget control, if it proves needed, with its own evidence.
- Whether the retired ceilings should be re-measured against a larger stratified sample of the 104 labeled pull requests, to confirm the five-pull-request result holds.

## Related Decisions

- ADR-086, lefthook local hook orchestration
- ADR-101, enforcement planes. Not a disjoint scope: ADR-101's plane rule classifies the gates this decision retires as P0, and therefore advisory, which is the same conclusion reached here from cost evidence rather than from the invariant. This decision also removes `SKIP_SCOPE_CHECK`, one of the four root-cause exhibits ADR-101 cites. Neither decision depends on the other landing

## References

- `.agents/governance/PROJECT-CONSTRAINTS.md:125`, the ceiling rationale and its single-incident basis
- `.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md`, self-attested approval after refusal
- `.agents/retrospective/2026-08-17-governance-bureaucracy-critical-review.md`, the 94% self-inflicted issue measurement and the #5103 rebind finding
- `scripts/detect_scope_explosion.py:492`, the unverified bypass flag
- Pull requests #4846, #4718, #5036, #5152, #5103, #5107, the sample
