---
source: wiki/concepts/Engineering Pitfalls/Rewrite Regression.md
created: 2026-05-31
review-by: 2026-08-31
tailored-for: decision-critic
---

# Rewrite-Regression Check

> "First implementation: 10x faster. Three months later, after you have fully rewritten it, it is effectively baseline or worse. But in the beginning it was so good." -- paraphrase of Casey Muratori

## Principle

Rewrite wins are usually transient. The headline number gets benchmarked once against an empty surface. Then the original feature pressure starts adding back the abstractions, middleware, edge-case handling, telemetry, and security hooks that made the original code slow. By v1 the rewrite regresses to baseline or past it. The v0 number was a marketing graph, not an engineering graph.

This is the perf-regression cousin of the second-system effect (Brooks): the rewrite team rebuilds without the constraints that produced the original design. Casey's framing is sharper because it names the specific mechanism (features re-add) and the specific tell (only the v0 number is benchmarked).

## Decision Critique Application

This is a **halt criterion**, not a checklist. Apply it during **Verification** (Steps 3-4) whenever a decision under critique is a rewrite, refactor, or migration that lists improvement as part of its justification. The improvement can be performance, clarity, or maintainability; the same pattern applies to all three.

When you detect a rewrite-for-improvement decision, the critic MUST get answers to all five questions:

1. **What is the current number with all current features?** The real baseline, measured against the full feature surface, not a cleaned-up subset.
2. **What is the projected number on the rewrite at v0?** No extra features yet. This is the seductive number; treat it as the least informative one.
3. **What is the projected number on the rewrite at v1?** After every current feature is re-added: middleware, error handling, telemetry, accessibility, i18n, security hooks, edge cases.
4. **What is the regression plan if v1 lands at baseline or worse?** Specifically, is there a budget (perf budget, complexity budget, readability gate) that blocks merge if the rewrite regresses below the baseline number?
5. **What is the institutional incentive that produced the original problem?** If nothing has changed about how features get added or reviewed, the rewrite will accumulate the same friction and regress the same way.

## Halt Rule

If the proposer can answer only question 2 (the v0 win) and cannot answer 1, 3, and 4, **halt the decision**. Do not rubber-stamp it. Return verdict ESCALATE (the v0-only case is the strongest halt: there is no engineering evidence yet) with the missing questions named. Partial-answer cases map to REVISE per the table below.

The rewrite is being evaluated on a marketing graph, not an engineering graph. The proposer has measured the rewrite against an empty surface and projected nothing about what happens when the features come back.

| Answered | Verdict |
|----------|---------|
| Only #2 (v0 win) | HALT: ESCALATE. v0 alone is not evidence. |
| #1, #2, #3, #4 | Math is done. Proceed to normal critique only after also resolving #5 below; an unanswered #5 caps the verdict at a flagged STAND, not a clean one. |
| #1, #2, #3 but no #4 | REVISE: add the regression budget before approval. |
| #1, #2 but no #3 (and/or no #4) | HALT: REVISE. The v1 projection is the load-bearing number; the v0 win alone is not engineering evidence. |
| #5 unanswered | Flag: the friction that caused the original problem is unaddressed. |

This is not a ban on rewrites. The check is "have you done the math," not "do not rewrite."

## Worked Example 1: Performance Rewrite

**Decision under critique:** "We should rewrite the request router in Rust. The prototype is 10x faster than the current Go router."

Apply the five questions:

1. **Baseline with all features?** Current Go router does auth, rate limiting, tracing, retries, and canary routing. Measured p99 is 12 ms. The proposer did not measure this; they compared against a bare router.
2. **v0 number?** The Rust prototype does plain path matching only. p99 is 1.2 ms. This is the 10x claim.
3. **v1 number?** Unknown. No projection exists for p99 after auth, rate limiting, tracing, retries, and canary routing are re-added. Each of those was a feature that landed on the Go router over two years.
4. **Regression plan?** None. No perf budget blocks merge if the Rust router lands above 12 ms once features return.
5. **Institutional incentive?** Same product team, same feature cadence, same reviewers. The pressure that grew the Go router to 12 ms is unchanged.

**Verdict: HALT (ESCALATE).** The proposer answered only question 2. The 10x number is the v0 win against an empty surface. Require questions 1, 3, and 4 before reconsidering. Recommended: set a perf budget at p99 <= 8 ms with all current features re-added; if the rewrite cannot project that, the win is transient.

## Worked Example 2: Clarity Rewrite

**Decision under critique:** "We should rewrite the legacy billing module. The current code is 4,000 lines and unreadable; the rewrite will be clean and maintainable."

The same temporal pattern applies. The "clean" v0 has not yet absorbed the edge cases that made the original messy.

1. **Baseline with all features?** The 4,000 lines encode tax rules for 14 jurisdictions, three proration policies, dunning, refunds, and two legacy contract types. Complexity is high because the domain is.
2. **v0 number?** The rewrite is 600 lines and reads cleanly. It handles the happy path and one jurisdiction.
3. **v1 number?** Unprojected. Once all 14 jurisdictions, both legacy contract types, dunning, and refunds are re-added, the line count and branching will climb. Past experience says it lands near the original size because the original size reflected the domain, not poor coding.
4. **Regression plan?** None. No readability gate blocks merge if the rewrite ends up as tangled as the original once the edge cases return.
5. **Institutional incentive?** The same audit and compliance pressure that added each jurisdiction rule will add them again. Nothing has changed about how the rules arrive.

**Verdict: REVISE.** The clarity claim is unfalsifiable until v1 is projected against the full feature surface. Recommended: define a maintainability measure (cyclomatic complexity per function, time to add a new jurisdiction) with a baseline and a failure threshold; require the v1 projection before approval. The original "mess" may be Chesterton's Fence: the edge cases are load-bearing.

## Cross-Links

- **programming-advisor**: search existing solutions before a rewrite. A library or an in-place fix may capture the win without the regression risk.
- **chestertons-fence**: understand why the original is slow or messy before ripping it out. The abstractions you remove may be the ones the features will force back.
- **Gall's Law**: prefer evolving the working system over a designed-from-scratch replacement.
- **Falsifiability**: a rewrite-for-clarity claim is unfalsifiable until the maintainability measure and threshold are named.
