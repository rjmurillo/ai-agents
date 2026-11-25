# Policy-driven PR approvals

Status: Proposed. Owner: Richard Murillo. Scope: ai-agents on GitHub.

## Step 0 First Principles

### Q1 Demand Reality

Richard requested this spec on 2026-11-24. No other requester is claimed.

### Q2 Status Quo

Review the changes, run the quality axes, then work the review threads.
Check merge readiness before enabling auto-merge or merging the reviewed head.
When a human decision is needed, route the PR to the maintainer.
Reframing: automation only. Separate approval from merge readiness.

### Q3 Desperate Specificity

Richard lacks a way to delegate routine approval under a repository-owned rule.
The current loop can decide readiness without recording a policy approval.

### Q4 Narrowest Wedge

Replay one narrow docs class, then observe it with verdict comments.
Allow four AI-assisted engineering hours for the first offline replay spike.
The estimate excludes human labeling, GitHub verification, and production enforcement.

### Q5 Observation

Ruleset `11104075` required zero approvals on 2026-11-24.
The existing merge gate contains no policy-based approval decision.
The former owner-comment verifier was retired after repeated approval rounds.
[ADR-125](../architecture/ADR-125-exact-code-quality-review-approvals.md#amendment-2026-11-24-owner-comment-approval-retired) records the cost.
No baseline for avoidable human review time has been measured.

### Q6 Future-fit

At ten times the volume, deterministic rules still need no model calls.
Bound spend, deduplicate events, and measure the human queue before expansion.

## Problem and outcomes

The repository can review and merge PRs automatically. It lacks delegated approval rules.
Give maintainers a default-branch policy that grants narrow approval or routes to a human.

- As maintainer, I see which rule, review evidence, and head justified approval.
- As an author, I see why the layer held my PR and who can unblock it.
- As an operator, I can stop automation without relaxing any existing protection.

## Prior art and constraints

Repository sources were checked against `main` at `faeeb6db92` (2026-11-24).

| Source | What stays in place |
|---|---|
| [pr-autofix gate](../../src/claude/skills/pr-autofix/SKILL.md#ready-to-merge-definition-4-conditions-all-required) | No conflict, required checks pass, threads addressed and resolved, acceptable merge state. |
| [Exact-head merge helper](../../src/claude/skills/github/scripts/pr/merge_pr.py#L22) | Full send still merges only the reviewed head. The approver never merges. |
| [Review marker verifier](../../scripts/validation/validate_review_marker.py#L3) | The marker binds the report digest and verdicts to the reviewed commit. It is not a GitHub review. |
| [#7512](https://github.com/rjmurillo/ai-agents/issues/7512), [#7514](https://github.com/rjmurillo/ai-agents/pull/7514), [#7538](https://github.com/rjmurillo/ai-agents/pull/7538) | The old verifier bound owner approval to exact SHAs and regression rows. It was deleted. Do not restore the comment protocol. |
| [CODEOWNERS](../../.github/CODEOWNERS) | Requests owner review on selected paths. GitHub does not enforce owner approvals under the current ruleset. |
| [CodeRabbit handling](../../src/claude/skills/pr-autofix/SKILL.md#stale-bot-changes_requested-review) | Its approval can clear its prior objection. `COMMENTED` cannot. The policy cannot dismiss reviews or replace its verdict. |

Live `main` uses ruleset `11104075`; classic protection returned `404 Branch not protected`.
It requires zero approvals, resolves conversations, and dismisses stale approving reviews.
Code-owner review, last-push approval, and strict up-to-date checks are off.
Keep the existing repository-role bypass unchanged. Give neither service identity a bypass.

Required contexts (2026-11-24, ruleset `11104075`, Actions integration `15368`):
`Validate Path Normalization`, `Validate Generated Files`, `Validate PR`, `Validate PR title`,
`Analyze (actions)`, `Analyze (python)`, `Run Python Tests`, `Validate Plugin Version Bump`,
and `Check whole-tree count ratchets (blocking)`.
Discover applicable checks at runtime. Do not hard-code this snapshot as an allowlist.

[ADR-006](../architecture/ADR-006-thin-workflows-testable-modules.md) keeps logic in Python.
[ADR-080](../architecture/ADR-080-model-pin-justification-policy.md) governs justified pins.
[ADR-111](../architecture/ADR-111-skill-model-pins-project-per-harness.md) governs harness model inheritance.
[ADR-112](../architecture/ADR-112-risk-tiered-action-boundaries.md) governs unattended mutation authority.
[ADR-114](../architecture/ADR-114-agent-workflows-approval-and-non-blocking.md) keeps model workflows approval-gated and advisory.
[ADR-109](../architecture/ADR-109-template-first-plugin-distribution.md) and [ADR-119](../architecture/ADR-119-symlinked-dogfood-agents-and-skills.md) govern package boundaries.
[Plugin self-containment](../../templates/rules/plugin-self-containment.md#must) forbids undeclared upstream runtime dependencies.
This service is repository-side. It requires no plugin, shell hook, or harness installation.

[Fallback spec at PR #7539 head `325c3ba966` (2026-11-24)](https://github.com/rjmurillo/ai-agents/blob/325c3ba96631187cdcba64c36164bb8337660669/.project-toolkit/specs/SPEC-harness-agnostic-llm-fallback.md)
proposes a bounded `complete` call behind a transport interface.
It separates configured headless access from tool-less, opt-in subscription CLI calls.
It strips metered credentials from subscription CLI children and avoids hard-coded model IDs.
Some harnesses lack a proven tool-less route. None is required to evaluate deterministic rules.
Reuse the final transport contract and approved routes after they land.
Do not copy private eval adapters or the actionability heuristic's default verdict.
Until the dependency and authorization exist, classifier rules may only hold.

## Policy and decision contract

Use a single versioned TOML file at `.github/pr-approval-policy.toml`.
Load it from the live default branch at an immutable commit, never the PR branch.
Record its commit and content digest. Recheck the commit before posting.
A missing, invalid, unsupported, or ambiguous policy holds; never reuse cached permissive policy.

The closed schema has `schema_version`, a repository `mode`, `budget`, and `rules`.
Modes are `off`, `observe`, and `enforce`; a rule cannot exceed the repository mode.
Each rule declares a stable `id`, `mode`, `effect`, and an `all` selector.
Effects are `hold`, `allow`, or `classify`. No match means hold.
Selectors use repo-relative path globs, label predicates, author classes, and size limits.
They can require named review sources, verdicts, and extra green check contexts.
Use case-sensitive path segments: `*` matches within a segment and `**` across segments.
Allow rules match every changed path, including the old path on renames.
Hold rules match any excluded path. Require all supplied selectors to match.
Reject unknown keys, unknown classifier IDs, duplicate IDs, and invalid selector values.
Resolve overlap as hold first. Multiple eligible approval rules hold as ambiguous.

**Hard stops run before rules or model calls:**

- Hold policy edits, workflow edits, and sensitive paths for a human.
- Protect all effective CODEOWNERS paths, security-action paths, and approval trust roots.
- Include CODEOWNERS itself, workflow actions, smoke pins, credentials, hooks, and policy code.
- Union trusted security path inventories with fixed exclusions. Policy can only add exclusions.
- Hold known same-identity authors, including registered aliases and delegated identities.
- Hold when author provenance is missing, ambiguous, or conflicts with trusted records.
- Hold drafts, unmergeable conflicts, closed PRs, and targets outside the selected branch.
- Hold forks in the first release. Never execute or import candidate code.
- Require all required checks green, zero unresolved threads, and no outstanding veto.
- **A human `CHANGES_REQUESTED` always wins over any policy approval.**
- Treat unknown reviewer identity as human for vetoes, never as human for clearance.

Use each reviewer's latest effective submitted decision, not their latest comment.
A later `COMMENTED` review and a push cannot clear an outstanding change request.
Release a human veto only when that reviewer approves or a human dismisses it explicitly.
A bot veto holds until that bot clears it or a human dismisses it.
Accept positive review evidence only from trusted sources for the current head.
CodeRabbit approval may count as supporting evidence if policy explicitly names it.
It cannot count as human clearance or substitute for the policy approver.

Start with one observed deterministic rule for prose-only documentation.
Require a registered independent author, allowlisted paths, at most five changed files, and 100 changed lines.
Count additions plus deletions. Exclude executable examples, generated inputs, renames, and binary files initially.
Use only trusted label provenance for positive eligibility. Unknown label provenance never grants approval.

A `classify` rule may ask one narrow question on an otherwise eligible PR.
The classifier receives bounded, untrusted evidence and a trusted default-branch rubric.
It returns only JSON: `{"verdict":"pass|hold|abstain","reason":"short explanation"}`.
The value must be one enum member. Reject extra keys and reasons exceeding 240 characters.
`pass` satisfies only that rule's residue. Repository code makes the final decision.
The model has no tools, GitHub credentials, write authority, or ability to select another transport.
Never echo raw model output in PR comments. Use stable reason codes and vetted summaries.

## Evidence and state

| Entity | Identity and invariant |
|---|---|
| Policy revision | Repository ID, default branch SHA, policy digest. |
| Decision snapshot | Repository ID, PR number, head SHA, base and merge-base SHAs, policy revision. |
| Decision record | Snapshot, evidence fingerprint, rule ID, mode, verdict, and reason codes. |
| Approval receipt | Decision record plus GitHub review ID, approver ID, and verified review commit. |
| Budget ledger | Repository ID and PR number. Retries and new heads never reset lifetime spend. |
| Human clearance | Authorized independent reviewer and explicit decision for this exact head. |

Read [REST PR metadata and files](https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files),
[check runs](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference),
[commit statuses](https://docs.github.com/en/rest/commits/statuses),
[review states and commits](https://docs.github.com/en/rest/pulls/reviews),
and [GraphQL review thread resolution](https://docs.github.com/en/graphql/reference/pulls#pullrequestreviewthread).
Read the applicable rules, both check systems, publishers, labels, author ID, and account type.
Use GitHub's applicable head or test-merge commit as required for each context.
Require `success` for policy eligibility. Native `neutral` or `skipped` does not grant policy approval.
Never satisfy an app-bound context with another publisher's same-name result.
Unresolved outdated threads still count. An empty incomplete page is not evidence of zero.
Page to completion. Detect GraphQL errors, missing pages, inconsistent counts, and REST file limits.
Do not interpret absent patches as empty diffs. Hold when completeness cannot be shown.

Classify GitHub accounts by stable IDs, not login suffixes or commit author strings.
Use an operator-owned registry for dedicated humans, agent accounts, other bots, and dependency Apps.
GitHub `User` cannot prove a human acted. An ordinary account can front a harness.
GitHub cannot attest the harness used, private author delegation, or historical thread state.
Do not infer these from a PR body, label text, commit trailer, or model output.
Human clearance requires an authorized reviewer with an independently controlled credential.
If that separation cannot be demonstrated, use a maintainer-verified clearance record or hold.

## GitHub posting and enforcement

Use a dedicated repository-scoped GitHub App installation identity to submit `APPROVE`.
Give it pull-request write and necessary reads, no contents write, checks write, or administration.
Keep GitHub credentials outside classifiers and avoid the authoring identities' tokens.
The [review endpoint](https://docs.github.com/en/rest/pulls/reviews#create-a-review-for-a-pull-request)
accepts installation tokens, App user tokens, and fine-grained PATs with pull-request write.
A PAT for a bot user acts as that account. A personal PAT acts as its owner.
App user tokens represent their user. Changing tokens cannot evade GitHub's self-review limit.
Check both GitHub account equality and known shared principals before attempting to approve.

Posting a review and counting it toward protection are different capabilities.
[GitHub rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-a-pull-request-before-merging)
can require approvals from reviewers with write access, code owners, or an independent last-push reviewer.
A bot-user or personal token counts only if its account meets the applicable reviewer rules.
The installation token's ability to post does not establish counted App eligibility.
[CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
is read from the base branch. A generic bot approval cannot substitute for a required owner.
Do not give the App a code-owner role or remove any protection to make it count.

Observe posts a comment only; enforce may post an approval and expose a hold to merge consumers.
The current zero-review rule does not count approvals toward any minimum.
An enforced hold must cover native merges and existing automatic merge paths for governed PRs.
The proposed fence is an additional required, publisher-bound deterministic eligibility check.
A separate verifier identity publishes it. It has no approval or merge authority.
For governed PRs, it requires a valid policy approval receipt or eligible human clearance.
For an explicitly separate dependency route, it reports success as `NOT_GOVERNED`.
That result requires a trusted dependency App ID and reviewed scope configuration.
Unknown scope or incomplete evidence never passes. All other default-branch PRs are governed.
`NOT_GOVERNED` grants no approval and never bypasses other required checks.
A receipt requires a trusted review ID and successful replay of mandatory predicates.
The fence consumes the approval receipt, never raw model output or a model job conclusion.
This new required context is excluded only from the approver's prerequisite check set.
That avoids a cycle. It remains required for merge on governed PRs.
The verifier must not run PR code, trust PR edits, or allow a general bot approval to pass.

Before promotion, test a repository with protections equal to the existing ruleset.
Prove the App review is eligible under an added one-approval rule, without a bypass.
Then prove the chosen fence on the effective merge routes, including GitHub auto-merge.
Prove it cannot transfer a signal between PRs sharing a head or between different bases.
Prove vetoes and stops cannot lose a race to merge after a prior approval.
Respect existing administrator bypass semantics. Do not grant or rely on new bypasses.
A REST approval is not a compare-and-swap across reviews, labels, and policy.
A successful commit check can outlive a same-head input change.
Reconciliation reduces drift but does not prove an atomic merge hold.
If the fence cannot prove these invariants, keep observe-only. Do not ship weaker enforcement.
Richard must authorize the fence and resolve its interaction with ADR-114 before activation.

Before writing, serialize by PR and reread head, base, policy, checks, reviews, threads, and stops.
Any material difference invalidates the decision. Do not silently move it to another head.
Send REST `commit_id` explicitly and include the full SHA and decision ID in the review body.
Read back review ID, approver, state, and commit; reread the live PR and veto inputs.
Only a verified receipt enters the fence. No duplicate reviews on retries or unknown writes.
On uncertain writes, reconcile from server data before allowing another write.
On a new head, void the old receipt even if the diff stays identical.
GitHub dismisses stale reviews when the reviewed diff changes under the current rule.
Listen for changes and reconcile receipts. Flag stale GitHub reviews for human cleanup if needed.
Never dismiss another review and never use `CHANGES_REQUESTED` as a kill mechanism.

## Stops, limits, and failure paths

Use a maintainer-controlled `approval:stop` label for one PR.
Use an authorized `/pr-approval stop repo` comment on a pinned control issue for repository-wide stop.
Verify the comment author's stable ID and authority. Pin the issue ID outside the policy file.
Latch the stop. Removing the label or deleting a comment cannot resume automation.
Resume requires explicit maintainer authorization. Repository mode `off` also stops the layer.
Stops void receipts and halt model calls and approval writes. Human review stays available.
If the stop store or permissions are unreadable, hold. No cached green result.

Initial hard maximum per PR: three decision rounds, one classifier call, and $0.02 in model spend.
Apply a 15-second classifier deadline and reserve worst-case spend before sending a call.
Require measurable or enforceable caps. An unmeterable route stays off.
Count duplicate events once. Count every actual retry against applicable caps.
An admitted round may finish within its reservation, even after reserving the last call.
Exhaustion prevents new evaluation, not completion of that admitted round.
Event ingestion to record invalidation does not consume a decision round.
After exhaustion, keep invalidating old receipts. Route any new decision to a human.

| Failure | Required outcome |
|---|---|
| Classifier unreachable, timeout, refusal, malformed JSON, or rate limit | Hold. No alternate provider or decision promotion. |
| Partial GitHub data, missing permission, check publisher mismatch, unknown actor | Hold. Name the missing evidence. |
| Conflicting review or changed evidence during the decision | Stop posting. If the write already landed, invalidate the receipt and alert. |
| Missing or malformed policy, trust-root mismatch, or stale base | Hold. Do not use an older allow policy. |
| Approval POST or read-back uncertain | Hold authorization. Reconcile by snapshot and decision ID. |
| Kill switch activates during a write | Block receipt use and alert if a review appeared. Verify the race before enforcing. |

## Observe mode and evaluation

Observe never posts `APPROVED` or alters merge eligibility.
Post a deduplicated comment with `WOULD APPROVE` or `HOLD`, the head, rule ID, and reason.
Use one decision comment per evaluated head. Label it advisory.
Measure Richard's decision independently of model output where practical.
Retain repository and PR IDs, timestamps, head and base SHAs, policy digest, and input fingerprints.
Log evidence IDs, decision reasons, provider and model identifiers, latency, and capped usage.
Log the observed human decision and source, eligibility outcome, and write or read-back state.
Restrict audit access to operators. Retain online records for 90 days initially.
Do not log tokens, raw prompts, patches, sensitive labels, or unfiltered review text.

Name the corpus **ai-agents approval replay v1**.
Freeze a manifest of PR-head pairs from 2026-08-01 through 2026-11-24 UTC.
Sample ordinary merged PRs, reverted PRs, and PRs Richard explicitly held or rejected.
Stratify by rule class and decision. Include dependency PRs and hard-stop cases as controls.
Record inclusion, sampling seed, sources, immutable heads, and missing evidence per row.
Keep all heads of a PR in one split. Reserve November for a locked holdout.
Use only signals available before the human verdict. Never expose labels from the future.

A scoped, explicit decision by Richard is ground truth. Merge is not an approval label.
A revert flags a candidate for adjudication; it does not rewrite the original decision.
Use review events or a signed-off adjudication manifest with evidence for explicit historical decisions.
Blindly re-labeled cases are a separate study. Do not report them as original decisions.
Exclude unknown decisions or unreconstructable inputs from rates. Report exclusions and coverage.
In observe mode, use exact-head decisions only. Record whether Richard saw the policy comment.
Count each PR once per class in promotion stats. Select snapshots before looking at predictions.

- False-approve rate: `WOULD APPROVE / human hold`, restricted to human-hold cases.
- False-hold rate: `HOLD / human approve`, restricted to human-approve cases.
- Report both counts and denominators per class, exact confidence bounds, and approval coverage.
- Report reverted-case outcomes, excluded cases, time to verdict, and projected net maintainer minutes.
- Compare the deterministic baseline and classifier variant on identical locked cases.

During observe, time active approval-only work for each sampled PR using the current process.
Exclude code review, CI waits, and work that policy automation would leave in place.
Time exception handling, sampled verification, and rule maintenance as pilot costs.
Project savings from measured approval-only time on correctly approved cases, minus measured costs.
Normalize to 30 days. Count missing savings as zero; missing cost data blocks promotion.
Report estimates as projections. Recheck actual net minutes after an authorized enforcement pilot.

Per class, require zero false approvals in the locked replay and live observation.
Require 30 days of observe and 60 distinct traceable human-hold PRs across both sets.
At least ten holds must be prospective. Require at least 30 human-approve PRs in total.
Zero errors in 60 independent holds gives a one-sided 95% upper bound below 5%.
Also require false holds at most 20%, zero hard-stop violations, and full race-test passage.
Sparse classes stay in observe. Do not pool easy classes to promote a different class.
A classifier must recover at least ten percentage points of false holds on matched cases.
Reset the evidence window for material rule, prompt, model, or transport changes.
Promotion requires Richard's explicit sign-off on the report and an exact policy revision.

## Dependency disposition

Keep Renovate's existing auto-merge separate in the pilot.
It is a dependency merge policy, not evidence of a GitHub approval.
[#7521](https://github.com/rjmurillo/ai-agents/pull/7521) removed its remaining manual-merge exclusions.
[Current config](../../renovate.json#L54) includes workflow pins, smoke lockfiles, and devcontainers.
Do not post approvals for either dependency bot during the pilot.
[Dependabot's workflow](../../.github/workflows/dependabot-approve-and-auto-merge.yml#L33) only enables auto-merge.
It leaves workflow and smoke changes for manual merge. Its Renovate comment is stale.

Renovate remains governed by CI under the 2026-11-23 owner direction.
A separate rollout decision must reconcile that direction with a repository-wide human hold.
Do not quietly exempt sensitive Renovate changes under a fence that claims to cover them.
If the fence cannot preserve the separate route without that exception, remain observe-only.
If Richard later folds dependencies in, native automerge becomes merge transport only.
Hard exclusions must then require human clearance, regardless of the update tool.

[#7524](https://github.com/rjmurillo/ai-agents/pull/7524) fixed the four failures from #7521.
The two current test files passed 19 tests on 2026-11-24 at `ce18cc4d70`.
Keep those tests if Renovate remains separate. No repairs belong to this spec.
If the dependency policy changes later, update the tests with that change.
Prove workflow, smoke, and devcontainer updates cannot take an unintended merge path.

## Buy-vs-build and stop criteria

Core: who may approve which changes. Context: GitHub delivery and optional model transport.
Recommend a replay and a small in-repo decision engine only if evidence supports it.
Use GitHub reviews and existing review tooling. Do not buy a vendor-bound decision engine.
Native CODEOWNERS alone cannot express the full rule. Retain it as independent protection.
Claude Approvals provides a reference workflow. It does not meet the provider-neutral requirement.

Stop before implementation if an equivalent mechanism already exists.
Stop enforcement if counted reviews or a true hold require weakening any protection.
Stop the classifier branch if deterministic rules offer the same measured coverage.
Stop the rollout if observed volume cannot support promotion within 90 days.
Do not promote with projected net savings below 30 minutes per 30 days.
Stop enforcement if measured net savings fall below that bar in its first 30 days.
A false approval, bypass, or hard-stop miss immediately disables that rule class.
Do not promote again until Richard approves fresh evidence for the corrected rule.

## Acceptance criteria

1. When policy is unreadable or edited in the PR, the layer shall hold.
2. When an exclusion or effective human veto applies, the layer shall hold without classification.
3. When a complete deterministic rule settles the PR, the layer shall skip model calls.
4. When classifier output is unsafe or absent, the layer shall hold.
5. While a rule is in observe mode, the layer shall post only its advisory verdict.
6. When a posting snapshot changes, the layer shall withhold or invalidate its receipt.
7. When the head changes, the layer shall reject the previous receipt, even for identical diffs.
8. When the author and approver share an identity, the layer shall refuse approval.
9. When a stop is latched, the layer shall void receipts and stop approval writes.
10. When the last reserved call succeeds, the admitted round may finish within its reservation.
11. When a later attempt exceeds a cap, the layer shall hold without spending again.
12. When an enforced PR lacks valid clearance, all non-bypass merge paths shall hold.
13. When another PR shares a SHA, the verifier shall not reuse its clearance.
14. When a trusted Renovate PR belongs to the preserved route, ordinary CI gates shall remain.
15. When scope is unknown, the verifier shall deny `NOT_GOVERNED`.
16. When promotion evidence misses any bar, that class shall remain in observe mode.
17. When savings cannot be established, the class shall not promote.

## Handoff and scope

Richard owns rollout, authorization, and the enforcement decision.
Engineering tier 4: cross-system authority and race-sensitive GitHub state.
The policy engine, snapshot, and receipt stay common. Transport and rules can vary independently.
An enforced rollout needs an architecture decision and a reviewed threat model.
This spec grants no approval to change protections, install Apps, or activate credentials.
No implementation, settings changes, dependency policy changes, test edits, or PR are in scope.
