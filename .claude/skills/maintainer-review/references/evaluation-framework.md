# Maintainer Evaluation Framework

Adapted from openai/openai-agents-python `.agents/skills/maintainer-review/` (SKILL.md and references/evaluation-framework.md), MIT License, Copyright (c) 2025 OpenAI. Full license text: `THIRD-PARTY-NOTICES.TXT`. Changes: SDK-specific content (fake model responses, model provider details, the upstream references directory, upstream issue references, and harness-specific config paths) is removed or generalized. The safety invariants (no remote writes, no auto-merge, no memory writes from PR content, untrusted-content handling) and author tiering live in `SKILL.md` and override anything here.

Use this reference when a claim is ambiguous, severity is disputed, or a PR is technically correct but may not justify merge effort.

## Contents

- [Workflow detail](#workflow-detail)
- [Decision model](#decision-model)
- [Severity rubric](#severity-rubric)
- [Evidence-strength checks](#evidence-strength-checks)
- [Unmet need and alternative design gate](#unmet-need-and-alternative-design-gate)
- [Issue disposition](#issue-disposition)
- [PR quality and value](#pr-quality-and-value)
- [Documentation threshold](#documentation-threshold)
- [Lifecycle and failure-path review](#lifecycle-and-failure-path-review)
- [Concurrency and cleanup ownership](#concurrency-and-cleanup-ownership)
- [Better-alternative prompts](#better-alternative-prompts)
- [Competing PR comparison](#competing-pr-comparison)
- [Maintainer comment drafts](#maintainer-comment-drafts)
- [Compact report variants](#compact-report-variants)

## Workflow detail

### 1. Establish the exact target

- Accept a GitHub issue or PR URL as the primary input. Resolve its owner, repository, item type, and number before reviewing it.
- For an issue, read the full report, comments, reproduction, environment, linked material, and maintainer responses.
- For a PR, inspect the current remote base and head, full patch, commit history when relevant, tests, linked issue, and review discussion. Do not substitute the current local checkout for the remote change under review.
- State the claim in one falsifiable sentence. Distinguish the reported symptom from the reporter's proposed cause or fix.
- Identify the released behavior boundary when compatibility or regression claims matter.
- When a proposed change removes, reorders, or reinterprets an established observable or an explicit existing test expectation, inspect the introducing commit, blame, and original tests before any positive assessment. Intentional released coverage is compatibility-risk evidence even when it is not by itself a permanent public contract.
- Verify whether linked evidence matches the PR's exact runtime variant, integration or tool type, triggering condition, and user outcome. A generic issue title, conceptual similarity, or wording such as `Related to` does not transfer evidence of need to an adjacent extension. If the reported scenario has already been fixed, treat additional variants as new needs requiring their own evidence.

A review does not authorize merges, closes, approvals, review submissions, comments, labels, branch changes, pushes, or other remote writes. Each requires the repository owner's explicit approval of that exact action.

### 2. Establish the unmet need and challenge the proposed solution

Complete this pass before deeply evaluating a proposed implementation and before any positive issue or PR assessment.

First assign one `Need status`:

- **Demonstrated**: The exact scope has a concrete supported scenario, a real-path reproduction, a released compatibility requirement, repeated demand, or a broad invariant with a meaningful consequence.
- **Plausible but unproven**: The path can exist, but realistic dependency or runtime behavior, user reach, frequency, consequence, or demand is not established.
- **Already covered**: A reasonable supported workflow already satisfies the outcome.
- **Unsupported**: The outcome belongs outside the project contract or at a dependency, adapter, or caller-owned layer.

Only `Demonstrated` need may receive `Merge-worthy as-is` or `Merge-worthy after focused changes`. For `Plausible but unproven`, prefer `Needs evidence` or `Not worth completing`; for `Already covered` or `Unsupported`, prefer closure or the relevant simpler alternative.

Keep four decisions separate and record them before comparing implementations:

1. **Observation validity**: whether the reported output, state, or code-path difference is real.
2. **Downstream consequence**: what concrete user, operational, compatibility, or durable-state result changes because of it.
3. **Need status**: one of the four evidence classifications above.
4. **Issue action**: prioritize, accept, narrow, request evidence, or close.

A real observation can still have no demonstrated need and a `Close` action. Do not describe an issue as simply "valid" when only the observation is confirmed. If the downstream consequence is missing, do not choose among proposed semantic contracts, select a competing PR, or draft implementation changes yet.

Before assigning `Demonstrated`, require one of these evidence paths:

1. **Observed impact**: A supported scenario, real-path reproduction, or credible user report shows a meaningful user-visible, operational, compatibility, or durable-state consequence.
2. **Material prevention**: A supported or ordinary failure path can reach the condition, the violated invariant protects against intrinsically material harm, and a complete code-path trace or realistic probe establishes that consequence. A known incident is not required for this path.

For both paths, trace `realistic trigger -> supported execution path -> observable or durable effect`. A local intermediate inconsistency, constructible branch, redundant operation, defensive improvement, or theoretically cleaner invariant is not a demonstrated need without a meaningful downstream effect. A small diff, technically correct patch, or inexpensive test does not lower this threshold. Material preventive outcomes include security or privacy exposure, credential leakage, persistent data or state corruption, duplicate external side effects, unrecoverable compatibility breaks, deadlock or indefinite hangs, and realistically repeatable resource exhaustion.

For a representation-only change, identify one concrete consumer computation, decision, or persisted interpretation that differs before and after the patch, then establish why the current result is wrong. If the patch only changes list shape, placeholder presence, metadata, ordering, or terminology without recovering information or changing a meaningful consumer outcome, the need is not `Demonstrated`.

An ambiguous contract is not itself evidence that the contract should change. When multiple current shapes are released or intentionally test-covered, prefer no code change until a demonstrated outcome justifies selecting a different semantic contract. Do not choose one shape only because it is more symmetric or easier to explain.

When a report establishes only a harmless or speculative logic-level improvement, prefer `Not worth completing` or `Close` rather than requesting implementation refinements. Use `Needs evidence` only when a specific missing reproduction or consequence trace could realistically change the practical-impact decision.

1. Restate the desired user outcome without naming the requested API, class, file, option, or implementation. Separate the actual constraint from the reporter's preferred mechanism.
2. Trace the closest supported ways to achieve that outcome in the current release and current target. Inspect the owning code path, public API, tests, and relevant docs rather than assuming that an unfamiliar capability is missing. Consider configuration, composition, cloning, callbacks, extension points, adapters, and doing the work at a caller-owned layer.
3. Determine whether the report shows a capability gap, an ergonomics or discoverability problem, an unsupported use case, or no demonstrated problem. A more convenient spelling is not automatically a missing capability.
4. Compare the proposed solution against the strongest existing approach and at least one better-design candidate: no code change, clearer documentation or validation, a narrower fix, reuse of an existing abstraction, or enforcement at a more coherent shared boundary.
5. For each viable approach, compare whether it satisfies the concrete scenario, what new public or internal contract it creates, cross-path consistency, compatibility, and permanent maintenance cost.

Do not treat a test proving that new code can work as evidence that the feature is needed. A fake or mocked response, manually constructed payload, mock, or new regression test can establish code-path reachability and implementation correctness; it does not by itself establish realistic dependency or runtime behavior, user reach, frequency, practical consequence, demand, or a material preventive outcome.

API symmetry, naming consistency, and parity with an adjacent tool, dependency, or output type are design arguments, not evidence of need. Parity may justify work when it removes existing complexity or enforces a broad demonstrated invariant, but adding branches, tests, documentation, or public behavior requires independent practical justification.

Treat an explicit public `Literal`, enum, discriminated union, or equivalent static type restriction as evidence that other values are outside the supported contract. Avoid adding duplicate client-side runtime validation solely to reject values that the public type already excludes. Require evidence that the project itself ingests untyped data, that fail-fast behavior before side effects protects a documented contract or material invariant, or that the invalid value causes meaningful impact on a supported path. The host language's ability to bypass type hints, pass adversarial runtime objects, or mutate attributes after construction is not by itself sufficient reason to add permanent validation branches and tests.

When an upstream server or service already rejects an unsupported request, treat that boundary as the source of truth and avoid duplicating the same acceptance rules in the client. Add fail-fast client validation only when waiting for the server rejection creates a demonstrated, substantial pitfall or material efficiency problem, such as avoidable billable work, repeated network latency or resource consumption, an irreversible side effect or state mutation, or an error that arrives too late or is too opaque for reasonable correction. Prefer the server's evolving validation over copied dependency allowlists or constraints that can drift.

#### Synthetic edge-case and extreme-value gate

Do not accept an issue or PR whose need is established only by constructing values that ordinary supported producers cannot emit or that have no realistic origin in supported use. This includes non-finite numbers such as `NaN` or infinity, astronomically large magnitudes, impossible enum or discriminated-union members, manually corrupted typed objects, and direct helper calls that bypass the owning public or wire boundary. A unit test that reaches such a branch proves constructibility, not a problem worth maintaining code for.

Default these reports to `Close` or `Not worth completing`, even when the patch is small and technically correct, unless the evidence establishes at least one of the following:

1. A supported dependency, parser, public API workflow, or credible user report produces the exact value under realistic conditions.
2. The released public contract intentionally accepts the value category and ordinary caller code can generate it without first violating that contract.
3. A complete security trace shows that attacker-controlled input can cross an actual trust boundary and cause realistically exploitable resource exhaustion or another concrete security-boundary violation.

Claims such as "this could sleep forever," "this could overflow," or "this might disable a limit" are insufficient without proving the realistic source of the value and the complete supported path to the consequence. Do not treat a security label as an exception by itself: identify the trust boundary, who can control the input, how it reaches the project, and the concrete protected outcome. A malformed value from an actually untrusted wire boundary may justify a fix when that trace is complete; a hypothetical hostile dependency, monkeypatched object, or manually constructed payload does not by itself do so.

When this gate fails, do not spend review effort refining implementation, tests, or error wording. Recommend closing both the issue and its PR, if one exists, and state the exact real-world evidence that would justify reconsideration only when such evidence is plausible.

If the need is not `Demonstrated`, inspect the patch only far enough to understand its contract, risk, and maintenance cost. Do not turn implementation defects, missing tests, or documentation gaps into a request-changes recommendation, because those questions become merge-blocking only after the need gate passes. If the report provides no concrete scenario, the existing functionality appears sufficient, or the requested mechanism solves only a hypothetical convenience problem, prefer `Needs evidence`, `Close`, `Supersede with a simpler alternative`, or `Not worth completing` over designing the requested feature on the reporter's behalf.

### 3. Discover competing open PRs proportionally

Do this before deeply evaluating a specified PR. A PR URL selects the starting point, not necessarily the entire comparison set.

- Determine the primary issue from explicit closing keywords, linked issues, issue timeline or development links, PR body and comments, and the reproduced symptom. If the association is inferred rather than explicit, state the evidence.
- When an issue is explicitly linked, enumerate all open PRs that address it through the issue timeline, development links, cross-references, closing keywords, and ordinary references. Include draft PRs but label them as drafts.
- When no issue is linked, run a bounded duplicate search using the strongest two or three signals from the title, reproduction, violated invariant, and runtime path. Stop when additional queries are unlikely to produce a credible competing implementation.
- Exclude closed or merged PRs from the active comparison set, while using them as history when relevant.
- Do not group PRs merely because they mention the same subsystem. Require a shared issue, symptom, violated invariant, or materially overlapping fix.
- Record the search methods and candidate set internally. If repository access cannot establish completeness, say so instead of claiming that every open PR was found. Do not list unrelated search hits in the final report.

When multiple candidates exist, compare them on need coverage, runtime correctness, scope, implementation layer, tests, compatibility, complexity, readiness, remaining maintainer work, and whether useful parts can be combined. Prefer the best maintainable solution, not the first submission or the smallest diff by default.

### 4. Use a desk-review evidence flow

Always begin with a desk review. Inspect the concrete runtime path before judging a small change as either trivial or meaningful. Check callers, adjacent helpers, validation layers, fallback paths, and existing tests. Search history or documentation only when it changes the decision. Inspecting test code is part of the desk review; executing tests, imports, examples, reproductions, benchmarks, or service calls is a runtime probe.

This skill does not plan or execute runtime probes. Invoking this skill, asking for a review, a pr-opened routine trigger, or supplying an issue or pull-request URL does not authorize tests, imports, examples, reproductions, benchmarks, service calls, or another runtime-probe skill. If decision-relevant runtime evidence remains after desk review, keep the assessment preliminary and suggest a separate runtime investigation. State the unresolved question, why it could change the decision, the evidence needed, and an appropriate base, release, or known-good control. Do not provide an exact command, request approval, invoke another skill, or execute code from this skill.

For repository-specific runtime invariants, read the repository's own architecture records and governance docs for the affected boundary. Treat them as read-only during review, verify each claim against the current remote change, and do not edit them as a side effect of a review.

Use this evidence order:

1. Trace the closest existing supported capabilities and determine whether they already satisfy the underlying user outcome.
2. Inspect existing tests and complete the code-path trace, including the changed-behavior coverage and interleaving passes below when triggered, without executing code.
3. Compare the implementation and existing evidence with the released version, base branch, or known-good control without executing code.
4. If a decision-relevant runtime uncertainty remains, stop and suggest a separate runtime investigation using the evidence requirements below.

#### Desk review

Produce the result from static evidence:

##### Mandatory unmet-need and design pass

Before a positive assessment, complete the pass in step 2 and be able to state all of the following from concrete evidence:

1. The user outcome that current supported behavior cannot achieve.
2. The closest existing API or composition path and the exact reason it is insufficient.
3. Why the proposed behavior belongs at the chosen abstraction layer instead of a caller, adapter, validation, documentation, or existing extension point.
4. Why the proposed permanent contract is better than no code change and the strongest narrower alternative.
5. What real scenario, compatibility requirement, or repeated demand justifies the new maintenance surface.
6. Whether maintainers would choose to pursue the same work if no contributor had already supplied a patch.

If any answer is missing and could change whether code should exist at all, do not call the issue actionable or the PR merge-worthy. Request only the evidence needed to distinguish a genuine capability gap from a usage, discoverability, or solution-design problem. This is a product and architecture evidence gap, not a runtime-probe trigger by itself.

##### Mandatory changed-behavior coverage pass

After the need gate passes, run this pass before a positive PR assessment or a conclusion that no additional runtime investigation is needed when a patch rejects, drops, replaces, or reclassifies previously accepted input, output, or state.

1. Trace the full set of supported cases matched by the changed condition through the actual normalization, conversion, and consumer paths. Do not stop at the reported reproducer or the fields checked by the patch; inspect the existing processing paths for information or semantics the new condition overlooks. Identify what callers could previously read, persist, replay, or act on and what the head would return or raise instead.
2. Group affected dependencies, adapters, or producers by materially different representations and semantics. Verify those differences against the relevant dependency version and supported release boundary; current upstream code alone does not establish behavior in an older dependency. Shared interfaces or a fix in one adapter do not prove equivalent behavior in another. Investigate only groups the changed condition can affect, not an exhaustive dependency matrix.
3. Keep evidence of need separate from evidence of compatibility. Label contributor-reported live results, inspected test assertions, authoritative specifications, and independently observed runtime results accurately. A reproduction from one dependency can demonstrate the bug without establishing that the new condition preserves other supported output shapes. A unit test using a constructed response does not establish which dependencies emit that response.

Record a compact working note for each materially different case: `trigger and representation -> base/head outcome -> caller consequence -> evidence and remaining uncertainty`. An omitted case is unfinished review work, not evidence that no runtime concern exists. Complete the static trace first. If it proves a supported regression, request the focused correction without requiring a live reproduction. If a concrete dependency-dependent uncertainty could change compatibility or the recommendation, keep the assessment preliminary and identify the focused runtime evidence and control needed under the existing desk-review boundary. Do not turn generic dependency uncertainty into mandatory runtime testing.

##### Mandatory interleaving and ownership pass

Run this pass before any positive PR assessment when a patch adds, removes, or reorders cleanup, retry, reconnect, cancellation, listeners, shared futures or tasks, connections or streams, state flags, or mutable state across an `await`, callback, event, or deferred completion.

1. Name each shared resource or state value and enumerate every path that can mutate it, including distinct public methods and wrapper or delegate paths. Include listeners, futures, tasks, connections, streams, locks, caches, state flags, persistence, and telemetry.
2. Trace at least two overlapping operations, `A` and `B`, across every suspension or re-entry point. Choose `B` from the strongest distinct mutator, not only a second invocation of `A`. Check `A pending -> B starts -> A fails -> B succeeds`, `A pending -> B starts -> B fails -> A succeeds`, close or cancellation between setup and completion, and a stale completion arriving after newer work.
3. For snapshot-based cleanup or rollback, always trace `A snapshots -> A destructively mutates -> B commits newer state -> A rollback resumes`. Require the pre-`A` state plus `B`'s committed mutation to survive in the correct order, with persisted state, caches, indexes, flags, and related ownership state agreeing.
4. For every cleanup or rollback, identify the exact attempt and resource generation it is allowed to dispose. Require an ownership token, generation, identity check, compare-and-swap, transaction, proven serialization, or an equivalent invariant at the actual mutation boundary. Do not infer exclusivity from intended usage; treat overlap as unsupported only when an explicit contract or fail-fast validation enforces that restriction.
5. Compare base and head for the survivor invariant. Replacing duplicated work with missing handlers, a closed shared resource, reverted state, or a failed surviving task is a regression, not successful cleanup. Do not dismiss stale cleanup as pre-existing when the patch newly invokes it for another failure, cancellation, or retry path.
6. Inspect tests for controlled interleavings using deferred futures, callbacks, or events. Require assertions about the failing and surviving operations' observable behavior and final resource coherence, not only listener counts or individual exception results.

Do not mark a concurrency-sensitive patch `Merge-worthy as-is` merely because sequential reconnect, retry, failure, and close tests pass. A triggered ownership pass is incomplete unless the evidence records the complete mutation surface, concrete ownership mechanism, strongest distinct-mutator interleaving, and survivor and coherence result. If the code trace proves an unsafe interleaving, conclude from static evidence and request a focused fix and regression test. If ownership remains ambiguous, keep the result preliminary and state the exact runtime evidence needed to resolve it.

- If the claim or PR is decisively negative from a complete reachable code-path trace, conclude the review without a runtime probe. Examples include an impossible or unsupported path, duplicated existing handling, a demonstrated no-op, a direct compatibility break, or a clearly wrong abstraction. Do not call an ambiguous result negative merely to avoid a probe.
- If the initial result is positive and there is no unresolved runtime concern, and the triggered changed-behavior coverage and interleaving passes are complete, the desk review may be sufficient for a final maintainer decision. Do not suggest additional runtime investigation only to restate evidence that cannot plausibly change the decision.
- If there is any unresolved runtime concern that could plausibly change claim validity, severity, merge-worthiness, required changes, or the preferred competing PR, report a `Preliminary assessment`. State the unresolved question, why it could change the decision, the evidence needed, and an appropriate control, then suggest a separate runtime investigation without planning or executing it.
- A purely stylistic, documentation, CI-status, or repository-readiness concern does not justify suggesting a runtime investigation unless it masks a runtime question.

Do not issue a definitive positive maintainer decision while a decision-relevant runtime concern remains unresolved. If the needed runtime evidence is unavailable or remains untested, keep the result preliminary and state the exact confidence limitation.

For changes involving validation, fail-fast behavior, cleanup, retries, interruption, or concurrency, trace lifecycle ordering in addition to the main behavior:

- Identify listeners, tasks, connections, files, locks, state mutations, and other resources acquired before the new check or failure point.
- Verify cleanup when construction, context-manager entry, validation, connection, or execution raises before normal teardown runs.
- Require a negative-path test when a failure can leave observable state or resources behind.

Do not over-investigate. Stop when additional evidence is unlikely to change validity, severity, or the maintainer recommendation.

### 5. Calibrate validity and impact

Use the sections below to assess claim validity, realistic reach, consequence, breadth, frequency, recoverability, compatibility, and severity. Keep observed facts separate from inference and state any missing evidence that could change the decision.

Report the `Need status` before classifying the need as a capability gap, ergonomics or discoverability gap, unsupported use case, or no demonstrated gap. Do not assign practical impact to the absence of the requested mechanism when an existing supported workflow already produces the requested outcome. Do not infer practical importance merely from reachability, API asymmetry, or a technically successful patch.

For a PR, make `Severity` describe the underlying issue or user need only. Do not combine it with the risk created by the proposed patch. Report a meaningful patch-induced regression, compatibility, lifecycle, or maintenance risk separately as `Patch risk`.

Do not infer that a report is low-value merely because an AI may have found or written it. Do not speculate about authorship or motive. Identify contribution-shaped reports through objective signals: no reproducible behavior, unrealistic inputs, an impossible call path, duplicated existing handling, tests that do not exercise the claim, or a fix whose runtime result is a no-op.

### 6. Apply the maintainer-effort test

Use the framework's issue dispositions and PR checks to decide whether the outcome justifies permanent code, tests, documentation, and maintainer attention. Classify code quality separately from repository readiness.

Use one code recommendation:

- **Merge-worthy as-is**: real need, sound implementation, proportionate scope, adequate tests.
- **Merge-worthy after focused changes**: real need and viable direction, with bounded corrections.
- **Supersede with a simpler alternative**: real need, but a smaller or more coherent fix is preferable.
- **Not worth completing**: negligible or unsupported impact, no-op behavior, wrong abstraction, or excessive completion cost.

`Merge-worthy as-is` and `Merge-worthy after focused changes` are invalid unless `Need status` is `Demonstrated`. A bounded set of implementation fixes cannot promote a `Plausible but unproven` need into a merge-worthy recommendation.

For `Merge-worthy as-is` and `Merge-worthy after focused changes`, use one repository-readiness status when it helps communicate the integration state:

- **Ready**: current head is reviewable and required checks are green.
- **CI or review pending**: code recommendation is stable, but required external gates are incomplete.
- **Rebase or conflict resolution required**: the head cannot merge cleanly or is materially stale.
- **Blocked**: a concrete external or repository condition prevents a reliable merge decision.

Omit repository readiness for `Supersede with a simpler alternative` and `Not worth completing`; CI, review, mergeability, or branch freshness does not change those dispositions. Put any validation limitation that materially affects confidence in the evidence instead. When readiness is included, use exactly one of the four statuses above and do not invent variants such as `ready mechanically` or use rebase status for semantic staleness.

Do not downgrade an otherwise sound code recommendation solely because CI is pending. Do not call a PR ready when semantic conflict resolution or material code changes remain.

When multiple open PRs address the same issue, make one portfolio-level recommendation: select the strongest PR, request focused changes in one candidate, combine specific ideas into one PR, supersede all candidates with a simpler approach, or close duplicates. Explain why the recommended path is better than each alternative without turning the report into line-by-line review.

Always compare the proposed patch with the strongest existing supported approach and at least one alternative: no code change, validation or documentation, a narrower fix, reuse of an existing helper, or a different layer that enforces the invariant consistently. A review is incomplete if it establishes only that the patch works without establishing why the current product cannot meet the underlying need and why this design is preferable.

When multiple plausible semantic scopes, compatibility boundaries, or public API contracts remain, do not ask the contributor to choose among maintainer-owned options. Decide the preferred scope from the evidence, compatibility contract, and product/API design principles, then request that specific change. If the evidence is insufficient to choose, mark the review preliminary or request maintainer input; do not present an open-ended implementation fork as the contributor's decision.

### 7. Report findings and maintainer action

Write the assessment in the language of the current conversation, English by default. Maintainer comment drafts remain English regardless of the assessment language. Keep the report decision-oriented and compact. Use no more than five evidence bullets by default; add more only when the decision genuinely depends on them.

Use the matching compact report variant below. While decision-relevant evidence is pending, use its preliminary-assessment variant and end with the evidence limitation and optional suggestion for a separate runtime investigation instead of presenting a final recommendation. Collapse sections for simple cases rather than padding the answer. Put unexpected or negative runtime findings first, and name the preferred PR or approach explicitly when candidates compete.

For PRs, put `Need status` before code recommendation. When the need is not `Demonstrated`, lead with that result, omit repository readiness, and avoid presenting patch fixes as the primary maintainer action.

When existing functionality or a better alternative materially affects the decision, state it explicitly in the evidence and recommendation. Name the exact supported path, what it does and does not cover, and why it is preferable. Do not bury a `Not worth completing` or `Supersede with a simpler alternative` conclusion beneath praise for implementation quality.

When recommending closure, requesting more evidence, requesting code changes, or superseding a PR, append the English, copy-paste-ready maintainer comment defined by the framework. If multiple PRs need different actions, label one draft for each affected PR. Include only merge-blocking requests in the main action paragraph; keep optional documentation or polish clearly non-blocking or omit it.

Before returning any maintainer comment draft, perform a GitHub paste-readiness pass using the repository's `AGENTS.md` and the Maintainer comment drafts section below. In the draft, use `#123` for same-repository issues or PRs and `owner/repo#123` for cross-repository references. Remove Markdown-linked issue or PR labels, harness navigation links, local file links, harness-only citation markers or footnotes, and app directives from the copy-ready draft. Preserve ordinary descriptive links to API docs, design notes, and other targets without native GitHub issue or pull-request syntax.

Also perform an action-delta pass. Every imperative sentence must correspond to a concrete difference between the current remote head and the desired state. Remove requests to "keep", "preserve", document, test, or change behavior that the current head already satisfies or that is not merge-blocking. A `Merge-worthy as-is` result must not contain change-request language. Keep portfolio comparisons out of a contributor-facing draft unless duplicate or supersession handling is the action for that target.

For request-changes comments, phrase maintainer-owned semantic decisions as a directive, not as a menu. It is fine to mention the rejected alternative briefly in the rationale, but the requested action must identify the chosen behavior, scope, or compatibility boundary. Use "please do X because..." instead of "either do X or Y" when X versus Y changes the project contract or user-visible semantics.

Do not produce a line-by-line review unless requested. Do not equate passing tests with merge-worthiness, or a logically correct patch with practical value.

## Decision model

Treat validity, severity, and merge-worthiness as separate results. Also distinguish a `Preliminary assessment`, which may still require decision-relevant evidence, from a final `Maintainer decision`. Do not label a provisional positive result as a verdict or final decision.

| Dimension | Questions | Strong evidence |
|---|---|---|
| Claim validity | Does the exact reported behavior occur? Is the proposed cause correct? | Reproduction, failing focused test, or complete reachable code path |
| Reachability | Can supported, realistic inputs reach it? | Public API trace, real configuration, linked user report, or release comparison |
| Consequence | What fails, and is the result silent or recoverable? | Observed output/error/state plus downstream effect |
| Breadth | Who is affected? | Supported dependencies, platforms, versions, and configurations identified precisely |
| Frequency | Is this normal, intermittent, or pathological? | Repeat runs, telemetry or reports when available, deterministic preconditions |
| Need status | Is the exact scope demonstrated, merely plausible, already covered, or unsupported? | Observed impact or a complete realistic trigger-to-material-consequence trace for prevention |
| Unmet need | What user outcome cannot be achieved through supported behavior today? | Concrete scenario plus a trace showing why the closest existing path is insufficient |
| Existing capability | Can configuration, composition, cloning, callbacks, extension points, or a caller-owned layer already satisfy the outcome? | Current release code, tests, docs, and an exact supported workflow |
| Compatibility | Is released behavior or durable state changed? | Latest release comparison and explicit contract inspection |
| Solution fit | Is the requested mechanism the best design and implementation layer? | Proposed solution compared with the strongest existing path and at least one narrower or more coherent alternative |
| Maintainer-owned scope | When several plausible semantics remain, which behavior should the project own? | A concrete maintainer decision grounded in compatibility, user outcome, and API design, not an open-ended contributor choice |
| Resource ownership | Can stale, failed, cancelled, or overlapping work mutate or clean up resources owned by surviving work? | Interleaving trace, attempt or generation ownership, and survivor assertions |
| Maintenance cost | What permanent complexity and review burden does it add? | Changed surface, new branches/configuration, test burden, remaining work |

## Severity rubric

- **Negligible**: No runtime difference, unreachable or unsupported input, cosmetic inconsistency, or a fully harmless edge case. Usually close, document, or decline code complexity.
- **Low**: Real but narrow and recoverable behavior with a simple workaround and no data, security, or compatibility risk. Merge only when the fix is small and clearly improves an invariant.
- **Moderate**: Plausible supported use fails or produces incorrect behavior for a meaningful subset of users. Prioritize a bounded fix and regression test.
- **High**: Common or important supported use is broken, causes serious compatibility problems, leaks sensitive data, or risks persistent corruption. Treat as urgent and require strong validation.
- **Critical**: Broadly exploitable security impact, severe data loss, or systemic failure requiring immediate coordinated action. Use only with concrete evidence.

Severity is approximately consequence multiplied by realistic reach and frequency, reduced by recoverability. Do not raise severity because a report sounds alarming or lower it because a patch is small.

## Evidence-strength checks

Before calling a claim confirmed, answer:

- Does the reproduction exercise the same public or internal path named in the report?
- Does the failure still occur on the relevant base, release, or current target?
- Does the test fail without the patch and pass with it?
- Are setup failures, stale builds, environment leakage, proxies, caches, or unsupported options excluded?
- Does an adjacent helper or equivalent path follow different semantics?
- Is the observed behavior prohibited by an actual contract, or merely surprising?
- If the patch removes or reinterprets an established observable or explicit test expectation, what did the introducing commit and original tests intend? Treat that history as compatibility-risk evidence, not automatic proof that the behavior must never change.
- For latency, timeout, buffering, backpressure, or cleanup claims, was observable elapsed time or a real state transition measured when feasible rather than inferred only from mocks?
- For shared asynchronous state, do tests control completion order and prove that stale failure or cleanup cannot affect the surviving operation?

Use `partially confirmed` when the symptom is real but the cause, reach, or claimed scope is wrong. Use `unproven` when decisive evidence is missing. Use `contradicted` only when evidence directly disproves the claim.

## Unmet need and alternative design gate

Issue reports often combine a desired outcome with a proposed API or implementation. Treat the proposed mechanism as a hypothesis. Confirm the unmet outcome before evaluating how well the patch implements that mechanism.

### Linked-evidence scope

Evidence from a linked issue applies only when the issue and PR share the same runtime variant, integration or tool type, trigger, supported configuration, and user outcome. A broad title, ordinary reference, `Related to` statement, or conceptual similarity is not enough. If an earlier change already resolved the concrete reported scenario, an adjacent extension starts with no inherited evidence of need.

### Need status

Assign one status before deep implementation review:

- **Demonstrated**: The exact scope has a concrete supported scenario, real-path reproduction, released compatibility requirement, repeated demand, or broad invariant with meaningful consequence.
- **Plausible but unproven**: The code path is possible, but realistic reach, frequency, consequence, dependency behavior, or demand is missing.
- **Already covered**: A reasonable supported workflow already satisfies the outcome.
- **Unsupported**: The outcome is outside the project contract or belongs at a dependency, adapter, or caller-owned layer.

Only `Demonstrated` need can support a merge-worthy code recommendation. `Plausible but unproven` maps to `Needs evidence` or `Not worth completing`, even when the patch is technically correct and its remaining fixes are bounded. `Already covered` and `Unsupported` normally map to closure or a simpler non-core alternative.

The need status is an evidence classification, not the issue action. Record observation validity, downstream consequence, need status, and issue action separately. A reported shape or branch difference can be confirmed while the need remains `Plausible but unproven` and the correct issue action is `Close`.

### Practical-impact gate

Do not accept a change merely because desk review identifies a local logical flaw, defensive improvement, or constructible edge case. Trace the complete consequence chain:

`realistic trigger -> supported execution path -> observable or durable effect`

A local intermediate inconsistency, redundant operation, surprising branch, or theoretically cleaner invariant is not a demonstrated need when it has no meaningful downstream effect. Reachability, a passing new test, a small diff, and low implementation cost establish neither practical impact nor maintenance value.

For representation-only changes, name the concrete consumer computation, decision, or persisted interpretation that changes before and after the patch. If the patch only changes list shape, placeholder presence, metadata, ordering, or terminology without recovering information or changing a meaningful result, it does not establish practical impact. Contract ambiguity and API symmetry are insufficient by themselves, especially when the current shapes are released or intentionally test-covered.

Use one of these evidence paths:

| Evidence path | Required proof | Insufficient proof |
|---|---|---|
| **Observed impact** | A supported scenario, real-path reproduction, or credible user report shows a meaningful user-visible, operational, compatibility, or durable-state consequence. | An internal state difference without a downstream effect, a synthetic branch, or a test that only proves the patch executes. |
| **Material prevention** | A supported or ordinary failure path reaches the condition; the violated invariant protects against intrinsically material harm; and a complete code-path trace or realistic probe establishes the concrete consequence and how the patch prevents it. | A statement that the condition "could" cause harm, an unsupported or malformed input, a mock-only scenario, or severity language without a complete consequence chain. |

A known incident, user report, frequency estimate, or production reproduction is not required for a material-prevention case. Require credible reachability and a concrete consequence such as security or privacy exposure, credential leakage, persistent data or state corruption, duplicate external side effects, an unrecoverable compatibility break, deadlock or indefinite hangs, or realistically repeatable resource exhaustion. Do not wait for those outcomes to occur before accepting a proportionate preventive fix.

When the trace ends in a harmless intermediate state, fully recoverable behavior without meaningful operational cost, theoretical cleanliness, or an unsupported scenario, classify the need as `Plausible but unproven`, `Unsupported`, or `No demonstrated gap` as appropriate. Prefer `Not worth completing` or `Close` over requesting implementation refinements. Use `Needs evidence` only when one specific missing reproduction or consequence trace could realistically change the practical-impact decision.

Before accepting an issue or recommending a PR, record:

| Question | Required evidence |
|---|---|
| What outcome is needed? | A concrete supported scenario stated without the proposed API or fix |
| What exists today? | The closest current-release API, configuration, composition, extension point, or caller-owned solution |
| Why is it insufficient? | An exact behavioral, compatibility, lifecycle, or operational constraint, not preference alone |
| What are the alternatives? | The proposed patch, the strongest existing path, and at least one no-code, narrower, or better-layer design |
| Why add a contract? | Practical benefit sufficient to justify public surface, runtime branches, cross-path tests, documentation, and long-term maintenance |

Classify the result:

- **Capability gap**: a supported, realistic outcome cannot be achieved with current functionality. Code may be warranted.
- **Ergonomics or discoverability gap**: the outcome is already possible, but the supported route is confusing or unnecessarily difficult. Prefer documentation, validation, or a narrowly justified convenience improvement.
- **Unsupported use case**: the desired outcome lies outside the project contract or belongs at a dependency, adapter, application, or other caller-owned layer. Do not expand the core API merely to make it possible.
- **No demonstrated gap**: no concrete scenario proves that existing functionality is insufficient. Request evidence or close rather than designing from the proposed mechanism.

Passing tests for a new implementation establish feasibility and correctness, not need. A fake or mocked response, manually constructed payload, mock, or synthetic fixture does not establish realistic dependency or runtime behavior, user reach, frequency, consequence, or demand. API symmetry and parity with an adjacent runtime are design arguments, not need evidence. A technically coherent patch can still be `Not worth completing` when the motivating scenario is hypothetical, already supported, or better solved elsewhere.

Use the counterfactual maintainer test: if the PR did not already exist, would maintainers choose to file and implement the same work from the available evidence? Contributor effort lowers implementation cost but does not create product need or remove permanent maintenance cost.

When the need is not `Demonstrated`, inspect implementation only far enough to estimate contract, risk, and maintenance cost. Do not convert patch defects, missing tests, or documentation gaps into a request-changes disposition; those become merge blockers only after the need gate passes.

## Issue disposition

Choose one primary action:

- **Prioritize**: confirmed moderate-or-higher impact or an important invariant with no safe workaround.
- **Accept, low priority**: confirmed low impact, existing supported functionality is insufficient for the demonstrated scenario, and a proportionate fix appears possible.
- **Narrow scope**: a valid core exists, but the report overstates affected paths or expected behavior.
- **Needs evidence**: plausible claim, but no minimal reproduction, supported setup, contract basis, or concrete scenario showing why existing functionality is insufficient.
- **Close**: duplicate, unsupported, unreachable, contradicted, no-op, already addressed by a reasonable supported path, or not worth permanent complexity.

When requesting evidence, ask only for information that could change the disposition.

For external contribution triage, default a `Plausible but unproven` need to `Close` when the current report shows only a logic-level or representation-level inconsistency. Use the `Needs evidence` issue action only when maintainers intentionally want to keep the issue open and can name one bounded piece of evidence likely to change the decision. A closed issue may still state the concrete evidence that would justify reconsideration.

## PR quality and value

Assess these independently:

1. **Need**: Same-scope evidence demonstrates either observed practical impact or a material preventive outcome that the closest supported capability cannot reasonably address. Do not inherit evidence from an adjacent variant or already-fixed scenario.
2. **Correctness**: The fix works for the reported case and meaningful boundaries.
3. **Placement**: The invariant is enforced once at the right layer instead of duplicating existing functionality, patching locally, or moving caller- or dependency-owned policy into the core project.
4. **Consistency**: Equivalent sync/async, streaming/non-streaming, integration, serialization, and resume paths remain aligned where applicable.
5. **Tests**: A regression test fails on the base, passes on the head, and tests the exact non-happy-path value or state. When shared state crosses an asynchronous boundary, tests control relevant completion orders and assert the surviving operation's behavior and final resource state.
6. **Compatibility**: Released public APIs, wire formats, persisted schemas, and established error behavior are preserved or intentionally migrated.
7. **Proportionality**: Complexity and public surface are justified by impact.
8. **Completion cost**: Remaining fixes, docs, tests, and design work are bounded enough to justify maintainer attention.

A PR can be correct but not merge-worthy. Typical reasons include a nonexistent or negligible need, an outcome already supported through a reasonable existing mechanism, a no-op on the actual runtime path, incomplete cross-path semantics, an abstraction cost larger than the benefit, or a simpler design at another layer.

Do not use implementation correctness, bounded remaining work, CI status, or contributor effort to upgrade a need that is only `Plausible but unproven`. Merge-worthiness is gated by demonstrated need, not by how close the patch is to completion.

Keep issue impact and patch risk separate. `Severity` describes the underlying issue or user need. A regression, compatibility break, lifecycle leak, or maintenance hazard introduced by the proposed patch belongs under `Patch risk` and must not inflate or obscure the issue severity.

When a PR exposes an ambiguous semantic boundary, decide whether that boundary belongs to maintainers before drafting requests. If the choice affects project contract, compatibility, persistence, error semantics, public API meaning, or cross-path behavior, the review should pick one direction or explicitly block on maintainer input. Do not delegate that choice to the contributor as "either X or Y"; ask for the chosen behavior and the tests or docs needed to lock it down.

## Documentation threshold

Do not treat documentation as automatically required for every public option, constructor parameter, dependency setting, or behavior change. Make docs merge-blocking only when at least one of these is true:

- Existing user-facing docs become materially false, unsafe, or misleading.
- Correct or safe use depends on a non-obvious constraint, migration step, compatibility boundary, or operational warning.
- Repository policy, the accepted issue scope, or an explicit maintainer decision requires documentation in the same PR and does not require separate release timing.
- The intended feature would be practically unusable or undiscoverable by its target users without a documented entry point, and generated API reference or clear code-level discovery is insufficient.

Decide documentation necessity separately from current-pull-request timing. If a repository documentation timing policy defers required `docs/` content because it would describe unreleased behavior, record the need as separately timed work and do not make its absence a blocker for the feature or bug-fix pull request.

If docs would merely improve discoverability or completeness, keep them non-blocking. Do not change `Merge-worthy as-is` to `Merge-worthy after focused changes` solely for optional docs, and do not include optional docs in the maintainer comment's required-action paragraph. Respect an explicit maintainer choice to omit docs or defer them to a separate follow-up.

## Lifecycle and failure-path review

Apply this section when a change adds validation, fail-fast behavior, cleanup, retries, interruption, background work, or concurrency.

- Identify the earliest point where all dynamic inputs needed for a correct decision are available.
- List side effects before and after that point: listeners, tasks, connections, files, locks, caches, state mutations, and telemetry.
- Exercise failure during construction, context-manager entry, validation, connection, and execution when those phases exist.
- Confirm that normal teardown is actually entered. If an enter or constructor fails, verify cleanup explicitly rather than assuming an exit hook runs.
- Prefer validation after dynamic configuration is resolved but before avoidable side effects begin.
- Require a regression test for any listener, task, connection, or state that could remain after failure.

## Concurrency and cleanup ownership

Apply this section before a positive assessment whenever lifecycle work crosses an `await`, callback, event, deferred completion, retry, reconnect, cancellation, or shared resource boundary. Sequential correctness is insufficient because a patch can improve isolated cleanup while introducing cross-attempt teardown.

Use a two-operation interleaving matrix during desk review:

| Ordering | Required question |
|---|---|
| `A pending -> B starts -> A fails -> B succeeds` | Can A's cleanup remove or revert anything B needs? |
| `A pending -> B starts -> B fails -> A succeeds` | Can B's cleanup leave A successful but non-functional? |
| `A succeeds -> B starts -> stale A completion` | Can stale A overwrite B's newer state or generation? |
| `A snapshots -> A mutates -> B commits -> A rolls back` | Does A restore only its own state while preserving B's commit, ordering, and derived state? |
| setup -> close/cancel -> late completion | Can late work resurrect listeners, state, tasks, or connections after teardown? |

For each ordering:

- Enumerate every path that can mutate the resource, including distinct public operations and wrapper or delegate paths. Choose `B` from the strongest distinct mutator rather than assuming a second invocation of `A` is sufficient.
- Identify the resource owner before and after every suspension point.
- Distinguish per-attempt resources from shared runner, session, transport, cache, or listener state.
- Require cleanup to carry an ownership token, generation, identity check, compare-and-swap, transaction, proven serialization guarantee, or another invariant at the actual mutation boundary that prevents cross-attempt disposal.
- Compare base and head on the survivor invariant. Fewer duplicates do not justify losing the only active handler, connection, task, or state update. Preserving or restoring `A` does not justify deleting, reverting, reordering, or hiding `B`.
- Require a controlled interleaving test when the ordering is reachable. The test must assert both the failing operation and the surviving operation's observable behavior after all completions settle, including agreement between persisted state and caches, indexes, flags, or other derived state.

An unscoped `finally`, `except`, close handler, cancellation callback, or rollback that mutates shared state after a suspension point is merge-blocking when another operation can still own or use that state.

Do not infer exclusive access from intended usage. Treat overlapping operations as unsupported only when documentation, public typing, construction-time validation, or fail-fast runtime enforcement establishes that restriction. Do not dismiss stale cleanup as pre-existing when a patch newly makes that cleanup reachable from another failure, cancellation, retry, or interruption path.

## Better-alternative prompts

Start with the strongest existing supported path, then test at least one additional alternative against the proposed patch. Do not complete a positive review without this comparison.

- Can the requested outcome already be achieved through configuration, composition, cloning, callbacks, extension points, a custom adapter, or caller-owned code?
- If the existing route is awkward, is the problem discoverability or ergonomics rather than missing capability?
- What happens if maintainers make no code change?
- Can input validation or an existing helper enforce the invariant earlier?
- Can the fix be limited to the one supported path that fails?
- Would documentation or a clearer error prevent misuse without runtime complexity?
- Can the test be added first to reveal the smallest correct change?
- Is the proposed public option compensating for an internal design issue?
- Is the proposed core behavior actually dependency- or application-specific policy that belongs at another layer?

## Competing PR comparison

When two or more open PRs address the same issue, first verify that they belong in one comparison set. Accept an explicit issue link, the same minimal reproduction, the same violated invariant, or materially overlapping runtime paths as association evidence. Do not treat a shared label or subsystem as sufficient.

Compare each candidate on the same evidence basis:

| Criterion | Question |
|---|---|
| Need | Does a concrete user outcome remain unmet after tracing existing supported functionality? |
| Existing capability | Could every candidate be avoided by configuration, composition, an extension point, or a better caller- or dependency-owned solution? |
| Coverage | Does it solve the whole confirmed issue, a useful subset, or an adjacent problem? |
| Correctness | Does the fix work on the real path and meaningful boundaries? |
| Placement | Does it enforce the invariant at the correct shared layer? |
| Tests | Does it reproduce the base failure and distinguish the candidate approaches? |
| Compatibility | Does it preserve released APIs, state, protocol, dependencies, and established behavior? |
| Complexity | What permanent branches, abstractions, configuration, or coupling does it add? |
| Readiness | Is it mergeable now, or how much focused work remains? |
| Reuse | Are there valuable tests or implementation pieces that should be combined into another candidate? |

Choose one portfolio-level disposition:

- **Prefer one PR**: identify the strongest candidate and close or supersede duplicates.
- **Prefer one after focused changes**: keep one candidate active and state bounded changes required before merge.
- **Combine selectively**: identify the destination PR and the exact ideas or tests worth transferring; avoid asking maintainers to reconcile entire competing implementations.
- **Replace all**: explain the simpler or more coherent implementation that should supersede every candidate.
- **Merge none**: the issue is invalid, negligible, unsupported, or none of the approaches justify completion cost.

Do not split the decision into independent approvals. Competing PRs consume overlapping review and maintenance budgets, so recommend one path for the issue as a whole.

## Maintainer comment drafts

Always write maintainer comments in English, regardless of the assessment language. Produce a draft when the recommendation is to close, request evidence, request focused code changes, supersede a PR, or choose one competing PR over another.

Keep each draft polite, direct, and copy-paste-ready. Usually use 60-160 words in one to three short paragraphs:

1. Acknowledge the contribution or report.
2. Explain the decision with the smallest amount of decisive technical evidence.
3. Give the exact next action or the condition for reconsideration.

Use GitHub-native references in every draft:

- Use `#123` for an issue or pull request in the same repository.
- Use `owner/repo#123` for an issue or pull request in another repository.
- Keep closing keywords native, for example `Fixes #123` or `Resolves #123`.
- Never wrap a native reference in a Markdown link. Write `#123`, not a Markdown link such as `[#123](...)`.
- Remove harness-only navigation links, local file links, harness-only citation markers or footnotes, and app directives from the draft. Preserve ordinary descriptive Markdown links for API docs, design notes, external resources, and GitHub targets that do not have native issue or pull-request syntax.

Before returning the draft, normalize any same-repository URL or qualified reference to `#<number>`, normalize any cross-repository issue or pull-request URL to `owner/repo#<number>`, and rescan the draft. Do not return it while a Markdown-linked issue or pull-request label, same-repository `<owner>/<repo>#<number>`, or bare GitHub issue or pull-request URL remains.

Perform an action-delta pass after the paste-readiness pass:

- Map every imperative sentence to a concrete difference between the current remote head and the desired state.
- Remove requests for behavior, tests, documentation, or scope that the current head already satisfies or that the recommendation does not require.
- Do not use change-request language for `Merge-worthy as-is`.
- Keep portfolio comparisons out of a contributor-facing draft unless that target is being closed or redirected as a duplicate or superseded implementation.

Do not include internal labels such as `severity: low`, speculate about AI authorship or contributor intent, repeat the full review, or soften the message until the requested action becomes unclear.

Do not ask contributors to choose maintainer-owned semantics. If two implementations are technically possible but one changes the project contract, decide the contract in the review and make the comment actionable. Use a short rationale such as "This keeps the new handler scoped to the existing raise site" or "This makes the handler name match all invalid final messages", then request the exact code and tests for that decision.

### Close

```text
Thanks for taking the time to investigate this. I traced the reported case through <path or behavior>, and <decisive finding>. In the supported path, <practical result>, so the added complexity is not justified by the demonstrated impact.

I am going to close this <issue/PR>. If you can provide <specific reproduction or evidence that would change the decision>, we can revisit the underlying problem with that narrower scope.
```

### Request changes

```text
Thanks for the contribution. The underlying issue is valid, and this approach is directionally reasonable. Before we can merge it, please address the following points: <bounded list of required changes>.

These changes are needed because <concise contract, lifecycle, compatibility, or test reason>. Once they are covered with a regression test that fails on the base and passes on the updated branch, the PR should be ready for another review.
```

Adapt the wording to the actual evidence. Do not use these templates as generic filler.

### Existing capability or better alternative

```text
Thanks for the contribution. I traced the underlying use case through <existing API or workflow>, which already supports <desired outcome and relevant limits>. The proposed change adds <new contract or complexity>, but the issue does not demonstrate a concrete supported case that the existing approach cannot handle.

I am going to close this <issue/PR> for now. If you can provide <specific scenario showing the existing approach is insufficient>, we can revisit the unmet need and choose the narrowest appropriate design from that evidence.
```

## Compact report variants

Use `Maintainer decision` for a concluded review. Use `Preliminary assessment` when a desk review is tentatively positive but a decision-relevant evidence gap remains. `Verdict` is intentionally avoided in the report headings because it does not communicate whether the result is provisional or final.

### Additional runtime investigation suggested

```markdown
## Preliminary assessment
<Tentative issue or PR assessment based on desk review only.>

## Static evidence
- <decisive code-path or test-inspection evidence>
- <what remains uncertain at runtime>

## Additional runtime investigation suggested
- Unresolved question: <the runtime uncertainty that could change the decision>
- Decision impact: <which validity, severity, scope, or recommendation could change>
- Evidence needed: <the observable behavior or state needed to resolve the uncertainty>
- Control: <base, release, or known-good comparison when relevant>

<Suggest a separate runtime investigation without providing an exact command, requesting approval, executing code, or invoking another skill. Do not present a final positive recommendation yet.>
```

### Issue

```markdown
## Maintainer decision
<Real/partial/unproven/contradicted, severity, and disposition.>

## Evidence
- <decisive evidence>
- <scope or uncertainty>

## Existing capability and alternatives
<Closest supported path, why it is or is not sufficient, and the preferred design alternative.>

## Recommendation
<Prioritize, accept low priority, narrow, request evidence, or close.>

## Maintainer comment draft
<Include when closure or additional evidence should be requested.>
```

### Pull request

```markdown
## Maintainer decision
<Need, practical impact, and merge-worthiness.>
- Need status: <Demonstrated / Plausible but unproven / Already covered / Unsupported>
- Code recommendation: <code disposition>
- Repository readiness: <integration status; include only for a merge-worthy recommendation when material>

## Evidence
- <runtime or code-path result>
- <test and compatibility result>

## Existing capability and alternatives
<Closest supported path, why the demonstrated scenario cannot use it, and why this patch is preferable to no code change or a narrower design.>

## Issue impact
- Validity: <claim validity>
- Severity: <severity of the underlying issue or need>
- Reach: <realistic reach>

## Patch risk
<Include only when the proposed patch introduces a meaningful regression, compatibility, lifecycle, or maintenance risk.>

## PR quality
- Solution fit: <assessment>
- Tests: <assessment>
- Remaining effort: <bounded/unbounded and why>

## Recommendation
<Merge, focused changes, simpler replacement, or close.>

## Maintainer comment draft
<Include only when closure, evidence, or changes should be requested.>
```

### Competing pull requests

```markdown
## Maintainer decision
<Issue validity, practical severity, and preferred implementation path.>

## Open PR comparison
| PR | Approach | Correctness | Tests | Compatibility/complexity | Readiness |
|---|---|---|---|---|---|
| #... | ... | ... | ... | ... | ... |

## Recommendation
<Select one, request focused changes, combine specific parts, replace all, or merge none.>
<State what should happen to every other open candidate.>

## Maintainer comment drafts
<One copy-paste-ready draft for each PR that should be closed, changed, or superseded.>
```
